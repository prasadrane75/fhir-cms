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


_graph: Neo4jClinicalGraph | None = None


def get_neo4j_graph() -> Neo4jClinicalGraph:
    global _graph
    if _graph is None:
        _graph = Neo4jClinicalGraph()
    return _graph
