import json

from langchain_core.tools import tool

from app.ai.tools.neo4j_tool import get_neo4j_graph


@tool
def query_clinical_knowledge_graph(query: str) -> str:
    """Query the Neo4j clinical knowledge graph for diseases, observations, interventions, and comorbidities."""
    graph = get_neo4j_graph()
    results = graph.query_clinical_context(query)
    if not results:
        return "No matching clinical knowledge found in the graph."
    lines = []
    for row in results:
        lines.append(
            f"Disease: {row.get('disease')} (ICD-10: {row.get('icd10')})\n"
            f"  Description: {row.get('description')}\n"
            f"  Monitored by: {', '.join(filter(None, row.get('observations', []))) or 'N/A'}\n"
            f"  Treatments: {', '.join(filter(None, row.get('interventions', []))) or 'N/A'}\n"
            f"  Related: {', '.join(filter(None, row.get('related_conditions', []))) or 'N/A'}"
        )
    return "\n\n".join(lines)


@tool
def get_reference_ranges(observation_codes: str) -> str:
    """Look up normal reference ranges for LOINC observation codes (comma-separated)."""
    codes = [c.strip() for c in observation_codes.split(",") if c.strip()]
    graph = get_neo4j_graph()
    results = graph.get_observation_reference_ranges(codes)
    if not results:
        return "No reference ranges found for the given codes."
    return "\n".join(
        f"{r['display']} ({r['code']}): {r['low']}-{r['high']} {r['unit']}" for r in results
    )


@tool
def check_claim_pricing_rules(payer_id: str, line_items_json: str) -> str:
    """Check claim line pricing against Neo4j payer contract rates and unit limits.

    line_items_json must be a JSON array of objects with keys:
    procedure_code (str), billed_amount (number), units (int, optional).
    """
    try:
        line_items = json.loads(line_items_json)
    except json.JSONDecodeError:
        return "Invalid JSON for line_items_json. Provide a JSON array of line items."

    if not isinstance(line_items, list):
        return "line_items_json must be a JSON array."

    graph = get_neo4j_graph()
    results = graph.check_claim_pricing_rules(payer_id, line_items)
    if not results:
        return "No pricing rules found for the submitted line items."

    lines = []
    for row in results:
        allowed = row.get("allowed_amount")
        allowed_display = f"${allowed:.2f}" if allowed is not None else "N/A"
        billed = row.get("billed_amount")
        billed_display = f"${billed:.2f}" if billed is not None else "N/A"
        lines.append(
            f"Procedure {row.get('procedure_code')}: {row.get('description') or 'unknown'}\n"
            f"  Billed: {billed_display} ({row.get('units', 1)} units)\n"
            f"  Allowed/contract: {allowed_display} (max units: {row.get('max_units') or 'N/A'})\n"
            f"  Pricing status: {row.get('pricing_status')}"
        )
    return "\n\n".join(lines)


@tool
def check_duplicate_claims(
    member_id: str,
    claim_id: str,
    service_date: str,
    procedure_codes: str,
) -> str:
    """Detect duplicate claims in Neo4j for the same member, date, and procedure codes.

    procedure_codes is a comma-separated list of CPT/HCPCS codes.
    service_date must be ISO format (YYYY-MM-DD).
    """
    codes = [code.strip() for code in procedure_codes.split(",") if code.strip()]
    graph = get_neo4j_graph()
    results = graph.check_duplicate_claims(member_id, claim_id, service_date, codes)
    if not results:
        return "No duplicate claims detected for the submitted service lines."

    lines = ["Potential duplicate claims detected:"]
    for row in results:
        amount = row.get("amount")
        amount_display = f"${amount:.2f}" if amount is not None else "N/A"
        lines.append(
            f"- Claim {row.get('duplicate_claim_id')} on {row.get('service_date')} "
            f"({row.get('status')}): procedure {row.get('procedure_code')} "
            f"({row.get('units', 1)} units, {amount_display})"
        )
    return "\n".join(lines)


PRIOR_AUTH_TOOLS = [query_clinical_knowledge_graph, get_reference_ranges]
CLAIMS_ADJUDICATION_TOOLS = [check_claim_pricing_rules, check_duplicate_claims]
ALL_REVIEW_TOOLS = PRIOR_AUTH_TOOLS + CLAIMS_ADJUDICATION_TOOLS
