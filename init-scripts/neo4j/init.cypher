// Sample clinical knowledge graph for grounding AI queries
CREATE (d1:Disease {name: 'Type 2 Diabetes Mellitus', icd10: 'E11', description: 'Chronic metabolic disorder characterized by insulin resistance'})
CREATE (d2:Disease {name: 'Hypertension', icd10: 'I10', description: 'Persistently elevated blood pressure'})
CREATE (d3:Disease {name: 'Chronic Kidney Disease', icd10: 'N18', description: 'Progressive loss of kidney function'})

CREATE (o1:Observation {code: '2339-0', display: 'Glucose', unit: 'mg/dL', normal_range_low: 70, normal_range_high: 99})
CREATE (o2:Observation {code: '8480-6', display: 'Systolic Blood Pressure', unit: 'mmHg', normal_range_low: 90, normal_range_high: 120})
CREATE (o3:Observation {code: '2160-0', display: 'Creatinine', unit: 'mg/dL', normal_range_low: 0.6, normal_range_high: 1.2})

CREATE (i1:Intervention {name: 'Metformin', type: 'medication', indication: 'Type 2 Diabetes'})
CREATE (i2:Intervention {name: 'Lifestyle Modification', type: 'behavioral', indication: 'Hypertension'})

CREATE (d1)-[:MONITORED_BY]->(o1)
CREATE (d2)-[:MONITORED_BY]->(o2)
CREATE (d3)-[:MONITORED_BY]->(o3)
CREATE (d1)-[:TREATED_WITH]->(i1)
CREATE (d2)-[:TREATED_WITH]->(i2)
CREATE (d1)-[:COMORBID_WITH]->(d2)
CREATE (d1)-[:RISK_FACTOR_FOR]->(d3);
