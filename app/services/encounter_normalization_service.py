from uuid import uuid4

from app.core.models.encounter import EncounterNormalizeRequest, EncounterNormalizeResponse, NormalizedCode

ICD10_MAP = {
    "E11": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "E119": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "I10": ("I10", "Essential (primary) hypertension"),
    "N18": ("N18.9", "Chronic kidney disease, unspecified"),
}

PROCEDURE_MAP = {
    "80053": ("80053", "Comprehensive metabolic panel"),
    "99285": ("99285", "Emergency department visit, high severity"),
    "36415": ("36415", "Routine venipuncture"),
}


class EncounterNormalizationService:
    def normalize(self, request: EncounterNormalizeRequest) -> EncounterNormalizeResponse:
        notes: list[str] = []
        diagnoses: list[NormalizedCode] = []
        procedures: list[NormalizedCode] = []

        for code in request.diagnosis_codes:
            key = code.strip().upper().replace(".", "")
            mapped = ICD10_MAP.get(key) or ICD10_MAP.get(key[:3])
            if mapped:
                diagnoses.append(
                    NormalizedCode(
                        source_code=code,
                        normalized_code=mapped[0],
                        code_system="ICD-10",
                        display=mapped[1],
                    )
                )
            else:
                diagnoses.append(
                    NormalizedCode(
                        source_code=code,
                        normalized_code=code.strip().upper(),
                        code_system="ICD-10",
                        display="Unmapped diagnosis code",
                    )
                )
                notes.append(f"Diagnosis code {code} passed through without local map entry.")

        for code in request.procedure_codes:
            key = code.strip()
            mapped = PROCEDURE_MAP.get(key)
            if mapped:
                procedures.append(
                    NormalizedCode(
                        source_code=code,
                        normalized_code=mapped[0],
                        code_system="CPT",
                        display=mapped[1],
                    )
                )
            else:
                procedures.append(
                    NormalizedCode(
                        source_code=code,
                        normalized_code=code,
                        code_system="CPT",
                        display="Unmapped procedure code",
                    )
                )
                notes.append(f"Procedure code {code} passed through without local map entry.")

        cms_ready = bool(diagnoses and procedures)
        if cms_ready:
            notes.append("Encounter normalized and CMS/Medicaid submission-ready.")
        else:
            notes.append("Encounter requires both diagnosis and procedure codes for CMS readiness.")

        return EncounterNormalizeResponse(
            transaction_id=uuid4(),
            member_id=request.member_id,
            patient_id=request.patient_id,
            cms_ready=cms_ready,
            normalized_diagnoses=diagnoses,
            normalized_procedures=procedures,
            validation_notes=notes,
        )


encounter_normalization_service = EncounterNormalizationService()
