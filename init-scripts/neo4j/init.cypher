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

// Claims adjudication knowledge graph (Capability 02)
CREATE (p1:Payer {id: 'PAYER01', name: 'Mock PPO Gold'})
CREATE (p2:Payer {id: 'PAYER02', name: 'Mock HMO Silver'})

CREATE (proc1:ProcedureCode {code: '99213', description: 'Office visit, established patient', allowed_amount: 125.00, max_units: 1})
CREATE (proc2:ProcedureCode {code: '80053', description: 'Comprehensive metabolic panel', allowed_amount: 45.00, max_units: 1})
CREATE (proc3:ProcedureCode {code: '93000', description: 'Electrocardiogram', allowed_amount: 35.00, max_units: 1})
CREATE (proc4:ProcedureCode {code: '36415', description: 'Routine venipuncture', allowed_amount: 12.00, max_units: 2})

CREATE (p1)-[:COVERS {contract_rate: 125.00}]->(proc1)
CREATE (p1)-[:COVERS {contract_rate: 45.00}]->(proc2)
CREATE (p1)-[:COVERS {contract_rate: 35.00}]->(proc3)
CREATE (p1)-[:COVERS {contract_rate: 12.00}]->(proc4)
CREATE (p2)-[:COVERS {contract_rate: 110.00}]->(proc1)
CREATE (p2)-[:COVERS {contract_rate: 40.00}]->(proc2)

CREATE (hc1:Claim {claim_id: 'CLM-1001', member_id: 'M1001', payer_id: 'PAYER01', service_date: '2026-08-01', status: 'paid'})
CREATE (hc2:Claim {claim_id: 'CLM-1002', member_id: 'M1001', payer_id: 'PAYER01', service_date: '2026-08-05', status: 'paid'})
CREATE (hc1)-[:BILLED {units: 1, amount: 125.00}]->(proc1)
CREATE (hc2)-[:BILLED {units: 1, amount: 45.00}]->(proc2);

// Care management and care gap analytics (Capability 07)
CREATE (m1:Member {member_id: 'M1001', name: 'Jane Doe', age: 58})
CREATE (m2:Member {member_id: 'M1002', name: 'John Smith', age: 67})
CREATE (m3:Member {member_id: 'M1003', name: 'Alice Johnson', age: 72})

CREATE (m1)-[:HAS_CONDITION {diagnosed_date: '2024-01-15'}]->(d1)
CREATE (m1)-[:HAS_CONDITION {diagnosed_date: '2023-06-01'}]->(d2)
CREATE (m2)-[:HAS_CONDITION {diagnosed_date: '2022-03-10'}]->(d1)
CREATE (m2)-[:HAS_CONDITION {diagnosed_date: '2024-11-01'}]->(d3)
CREATE (m3)-[:HAS_CONDITION {diagnosed_date: '2021-05-20'}]->(d1)
CREATE (m3)-[:HAS_CONDITION {diagnosed_date: '2020-08-12'}]->(d2)
CREATE (m3)-[:HAS_CONDITION {diagnosed_date: '2023-02-01'}]->(d3)

CREATE (m4:Member {member_id: 'M1002', name: 'Robert Martinez', age: 61, patient_id: 'P1002'})
CREATE (m4)-[:HAS_CONDITION {diagnosed_date: '2023-09-01'}]->(d1)
CREATE (m4)-[:HAS_CONDITION {diagnosed_date: '2022-04-15'}]->(d2)

CREATE (cm1:CareMeasure {measure_id: 'HEDIS_A1C', name: 'Annual A1C for Diabetes', lookback_days: 365, priority: 'high'})
CREATE (cm2:CareMeasure {measure_id: 'HEDIS_BP', name: 'Blood Pressure Control', lookback_days: 180, priority: 'medium'})
CREATE (cm3:CareMeasure {measure_id: 'HEDIS_CKD', name: 'Kidney Function Monitoring', lookback_days: 365, priority: 'high'})

CREATE (d1)-[:REQUIRES_MEASURE]->(cm1)
CREATE (d2)-[:REQUIRES_MEASURE]->(cm2)
CREATE (d3)-[:REQUIRES_MEASURE]->(cm3)

CREATE (m1)-[:COMPLETED_MEASURE {completed_date: '2026-01-10'}]->(cm1)
CREATE (m1)-[:HAS_OBSERVATION {value: 142, observed_date: '2026-01-10', unit: 'mg/dL'}]->(o1)
CREATE (m2)-[:COMPLETED_MEASURE {completed_date: '2026-05-01'}]->(cm1)

// Payment integrity graph (Capability 10)
CREATE (pay1:Payment {payment_id: 'PAY-1001', claim_id: 'CLM-1001', member_id: 'M1001', payer_id: 'PAYER01', amount: 125.00, payment_date: '2026-08-05', status: 'posted'})
CREATE (pay2:Payment {payment_id: 'PAY-1002', claim_id: 'CLM-1001', member_id: 'M1001', payer_id: 'PAYER01', amount: 125.00, payment_date: '2026-08-06', status: 'posted'})
CREATE (pay3:Payment {payment_id: 'PAY-1003', claim_id: 'CLM-1002', member_id: 'M1001', payer_id: 'PAYER01', amount: 45.00, payment_date: '2026-08-07', status: 'posted'})
CREATE (pay4:Payment {payment_id: 'PAY-1004', claim_id: 'CLM-2001', member_id: 'M1002', payer_id: 'PAYER01', amount: 125.00, payment_date: '2026-08-07', status: 'posted'})
CREATE (pay5:Payment {payment_id: 'PAY-1005', claim_id: 'CLM-2002', member_id: 'M1002', payer_id: 'PAYER01', amount: 125.00, payment_date: '2026-08-07', status: 'posted'})

CREATE (pay1)-[:PAYS]->(hc1)
CREATE (pay2)-[:PAYS]->(hc1)
CREATE (pay3)-[:PAYS]->(hc2);
