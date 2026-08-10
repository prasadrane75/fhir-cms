from typing import Any

from neo4j import GraphDatabase

from app.core.config import settings


class Neo4jClinicalGraph:
    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def query_clinical_context(self, query: str) -> list[dict[str, Any]]:
        """Search the clinical knowledge graph for diseases, observations, and interventions."""
        cypher = """
        CALL {
            MATCH (d:Disease)
            WHERE toLower(d.name) CONTAINS toLower($query)
               OR toLower(d.icd10) CONTAINS toLower($query)
               OR toLower(d.description) CONTAINS toLower($query)
            OPTIONAL MATCH (d)-[:MONITORED_BY]->(o:Observation)
            OPTIONAL MATCH (d)-[:TREATED_WITH]->(i:Intervention)
            OPTIONAL MATCH (d)-[:COMORBID_WITH|RISK_FACTOR_FOR]->(related:Disease)
            RETURN d.name AS disease,
                   d.icd10 AS icd10,
                   d.description AS description,
                   collect(DISTINCT o.display) AS observations,
                   collect(DISTINCT i.name) AS interventions,
                   collect(DISTINCT related.name) AS related_conditions
            UNION
            MATCH (o:Observation)
            WHERE toLower(o.display) CONTAINS toLower($query)
               OR toLower(o.code) CONTAINS toLower($query)
            OPTIONAL MATCH (d:Disease)-[:MONITORED_BY]->(o)
            RETURN d.name AS disease,
                   d.icd10 AS icd10,
                   d.description AS description,
                   [o.display] AS observations,
                   [] AS interventions,
                   [] AS related_conditions
        }
        RETURN disease, icd10, description, observations, interventions, related_conditions
        LIMIT 10
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"query": query})
            return [dict(record) for record in result]

    def get_observation_reference_ranges(self, observation_codes: list[str]) -> list[dict[str, Any]]:
        if not observation_codes:
            return []
        cypher = """
        MATCH (o:Observation)
        WHERE o.code IN $codes
        RETURN o.code AS code, o.display AS display, o.unit AS unit,
               o.normal_range_low AS low, o.normal_range_high AS high
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"codes": observation_codes})
            return [dict(record) for record in result]

    def check_claim_pricing_rules(
        self,
        payer_id: str,
        line_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Look up contract rates and pricing limits for claim line items."""
        if not line_items:
            return []

        cypher = """
        UNWIND $line_items AS item
        OPTIONAL MATCH (p:Payer {id: $payer_id})-[c:COVERS]->(proc:ProcedureCode {code: item.procedure_code})
        RETURN item.procedure_code AS procedure_code,
               proc.description AS description,
               proc.allowed_amount AS catalog_allowed_amount,
               proc.max_units AS max_units,
               c.contract_rate AS contract_rate,
               item.billed_amount AS billed_amount,
               item.units AS units,
               CASE
                   WHEN proc IS NULL THEN 'procedure_not_covered'
                   WHEN item.units > proc.max_units THEN 'units_exceed_max'
                   WHEN item.billed_amount > coalesce(c.contract_rate, proc.allowed_amount) THEN 'billed_exceeds_contract'
                   ELSE 'within_limits'
               END AS pricing_status,
               coalesce(c.contract_rate, proc.allowed_amount) AS allowed_amount
        """
        with self._driver.session() as session:
            result = session.run(
                cypher,
                {"payer_id": payer_id, "line_items": line_items},
            )
            return [dict(record) for record in result]

    def check_duplicate_claims(
        self,
        member_id: str,
        claim_id: str,
        service_date: str,
        procedure_codes: list[str],
    ) -> list[dict[str, Any]]:
        """Find prior claims that may duplicate the submitted service lines."""
        if not procedure_codes:
            return []

        cypher = """
        MATCH (existing:Claim)-[b:BILLED]->(proc:ProcedureCode)
        WHERE existing.member_id = $member_id
          AND existing.claim_id <> $claim_id
          AND existing.service_date = $service_date
          AND proc.code IN $procedure_codes
        RETURN existing.claim_id AS duplicate_claim_id,
               existing.service_date AS service_date,
               existing.status AS status,
               proc.code AS procedure_code,
               b.units AS units,
               b.amount AS amount
        ORDER BY existing.claim_id, proc.code
        """
        with self._driver.session() as session:
            result = session.run(
                cypher,
                {
                    "member_id": member_id,
                    "claim_id": claim_id,
                    "service_date": service_date,
                    "procedure_codes": procedure_codes,
                },
            )
            return [dict(record) for record in result]

    def calculate_comorbidity_risk_scores(
        self,
        member_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate comorbidity risk scores from member conditions and disease graph edges."""
        cypher = """
        MATCH (m:Member)
        WHERE $member_id IS NULL OR m.member_id = $member_id
        OPTIONAL MATCH (m)-[:HAS_CONDITION]->(d:Disease)
        WITH m, collect(DISTINCT d) AS diseases
        UNWIND CASE WHEN size(diseases) = 0 THEN [null] ELSE diseases END AS primary
        OPTIONAL MATCH (primary)-[rel:COMORBID_WITH|RISK_FACTOR_FOR]->(related:Disease)
        OPTIONAL MATCH (m)-[:HAS_CONDITION]->(related)
        WITH m, diseases, primary, rel, related,
             CASE
                 WHEN primary IS NULL THEN 0
                 WHEN related IS NOT NULL AND (m)-[:HAS_CONDITION]->(related)
                      AND type(rel) = 'RISK_FACTOR_FOR' THEN 3
                 WHEN related IS NOT NULL AND (m)-[:HAS_CONDITION]->(related)
                      AND type(rel) = 'COMORBID_WITH' THEN 2
                 WHEN type(rel) = 'RISK_FACTOR_FOR' THEN 1
                 WHEN type(rel) = 'COMORBID_WITH' THEN 1
                 ELSE 0
             END AS edge_score
        WITH m, diseases, coalesce(sum(edge_score), 0) + size(diseases) AS comorbidity_risk_score
        RETURN m.member_id AS member_id,
               m.name AS member_name,
               [d IN diseases | d.name] AS conditions,
               comorbidity_risk_score AS comorbidity_risk_score
        ORDER BY comorbidity_risk_score DESC, m.member_id
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"member_id": member_id})
            return [dict(record) for record in result]

    def find_care_gaps(self, member_id: str | None = None) -> list[dict[str, Any]]:
        """Find open care gaps where required measures are not completed within lookback."""
        cypher = """
        MATCH (m:Member)-[:HAS_CONDITION]->(d:Disease)-[:REQUIRES_MEASURE]->(measure:CareMeasure)
        WHERE $member_id IS NULL OR m.member_id = $member_id
        OPTIONAL MATCH (m)-[completed:COMPLETED_MEASURE]->(measure)
        WITH m, d, measure, max(completed.completed_date) AS last_completed
        WHERE last_completed IS NULL
           OR date(last_completed) < date() - duration({days: measure.lookback_days})
        WITH m, d, measure, last_completed,
             CASE
                 WHEN last_completed IS NULL THEN measure.lookback_days
                 ELSE duration.between(date(last_completed), date()).days
             END AS days_since
        RETURN m.member_id AS member_id,
               measure.measure_id AS measure_id,
               measure.name AS measure_name,
               d.name AS related_condition,
               measure.priority AS priority,
               CASE WHEN last_completed IS NULL THEN 'open' ELSE 'overdue' END AS gap_status,
               CASE
                   WHEN last_completed IS NULL THEN measure.lookback_days
                   ELSE days_since - measure.lookback_days
               END AS days_overdue
        ORDER BY measure.priority DESC, days_overdue DESC, m.member_id
        """
        with self._driver.session() as session:
            result = session.run(cypher, {"member_id": member_id})
            return [dict(record) for record in result]

    def find_duplicate_payments(
        self,
        member_id: str | None = None,
        payer_id: str | None = None,
        lookback_days: int = 90,
    ) -> list[dict[str, Any]]:
        """Detect duplicate payments on the same claim or repeated member/date/amount pairs."""
        cypher = """
        CALL {
            MATCH (p1:Payment)-[:PAYS]->(c:Claim)<-[:PAYS]-(p2:Payment)
            WHERE p1.payment_id < p2.payment_id
              AND p1.status = 'posted' AND p2.status = 'posted'
              AND ($member_id IS NULL OR c.member_id = $member_id)
              AND ($payer_id IS NULL OR p1.payer_id = $payer_id OR p2.payer_id = $payer_id)
              AND date(p1.payment_date) >= date() - duration({days: $lookback_days})
            RETURN 'duplicate_claim_payment' AS anomaly_type,
                   c.member_id AS member_id,
                   c.claim_id AS claim_id,
                   [p1.payment_id, p2.payment_id] AS payment_ids,
                   p1.amount + p2.amount AS total_amount,
                   p2.payment_date AS payment_date,
                   'high' AS severity
            UNION
            MATCH (p1:Payment), (p2:Payment)
            WHERE p1.payment_id < p2.payment_id
              AND p1.member_id = p2.member_id
              AND p1.payment_date = p2.payment_date
              AND p1.amount = p2.amount
              AND p1.claim_id <> p2.claim_id
              AND p1.status = 'posted' AND p2.status = 'posted'
              AND ($member_id IS NULL OR p1.member_id = $member_id)
              AND ($payer_id IS NULL OR p1.payer_id = $payer_id)
              AND date(p1.payment_date) >= date() - duration({days: $lookback_days})
            RETURN 'duplicate_member_payment' AS anomaly_type,
                   p1.member_id AS member_id,
                   null AS claim_id,
                   [p1.payment_id, p2.payment_id] AS payment_ids,
                   p1.amount + p2.amount AS total_amount,
                   p1.payment_date AS payment_date,
                   'medium' AS severity
        }
        RETURN anomaly_type, member_id, claim_id, payment_ids, total_amount, payment_date, severity
        ORDER BY severity DESC, payment_date DESC
        """
        with self._driver.session() as session:
            result = session.run(
                cypher,
                {
                    "member_id": member_id,
                    "payer_id": payer_id,
                    "lookback_days": lookback_days,
                },
            )
            return [dict(record) for record in result]

    def find_clinical_gap_payment_flags(
        self,
        member_id: str | None = None,
        payer_id: str | None = None,
        lookback_days: int = 90,
    ) -> list[dict[str, Any]]:
        """Flag high-priority open care gaps where payments were still posted."""
        cypher = """
        MATCH (m:Member)-[:HAS_CONDITION]->(d:Disease)-[:REQUIRES_MEASURE]->(measure:CareMeasure)
        WHERE measure.priority = 'high'
          AND ($member_id IS NULL OR m.member_id = $member_id)
          AND NOT EXISTS {
              MATCH (m)-[:COMPLETED_MEASURE]->(measure)
          }
        MATCH (pay:Payment {member_id: m.member_id})
        WHERE pay.status = 'posted'
          AND ($payer_id IS NULL OR pay.payer_id = $payer_id)
          AND date(pay.payment_date) >= date() - duration({days: $lookback_days})
        RETURN m.member_id AS member_id,
               m.name AS member_name,
               measure.measure_id AS measure_id,
               measure.name AS measure_name,
               pay.payment_id AS payment_id,
               pay.amount AS payment_amount,
               pay.payment_date AS payment_date,
               'high_risk_gap_with_payment' AS flag_type,
               CASE
                   WHEN size([(m)-[:HAS_CONDITION]->(dx:Disease) | dx]) >= 3 THEN 'critical'
                   ELSE 'high'
               END AS severity
        ORDER BY severity DESC, pay.payment_date DESC
        """
        with self._driver.session() as session:
            result = session.run(
                cypher,
                {
                    "member_id": member_id,
                    "payer_id": payer_id,
                    "lookback_days": lookback_days,
                },
            )
            return [dict(record) for record in result]


_graph: Neo4jClinicalGraph | None = None


def get_neo4j_graph() -> Neo4jClinicalGraph:
    global _graph
    if _graph is None:
        _graph = Neo4jClinicalGraph()
    return _graph
