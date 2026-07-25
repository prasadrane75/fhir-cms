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
