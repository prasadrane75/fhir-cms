from uuid import uuid4

from app.core.models.provider import ProviderValidationRequest, ProviderValidationResponse

PROVIDER_DIRECTORY = {
    "1234567890": {
        "name": "Dr. Sarah Chen",
        "tax_id": "12-3456789",
        "network_status": "active",
        "credentialing_status": "compliant",
    },
    "9876543210": {
        "name": "Dr. Legacy Provider",
        "tax_id": "98-7654321",
        "network_status": "inactive",
        "credentialing_status": "expired",
    },
}


class ProviderValidationService:
    def validate_provider(self, request: ProviderValidationRequest) -> ProviderValidationResponse:
        notes: list[str] = []
        npi = request.npi.strip()
        record = PROVIDER_DIRECTORY.get(npi)

        if not record:
            notes.append("NPI not found in master provider directory.")
            return ProviderValidationResponse(
                transaction_id=uuid4(),
                npi=npi,
                network_status="not_found",
                credentialing_status="pending",
                validation_notes=notes,
            )

        if request.tax_id and request.tax_id.replace("-", "") != record["tax_id"].replace("-", ""):
            notes.append("Tax ID mismatch against provider directory record.")

        network_status = record["network_status"]
        credentialing_status = record["credentialing_status"]
        if network_status == "active" and credentialing_status == "compliant":
            notes.append("Provider validated for active network participation and credentialing compliance.")
        else:
            notes.append("Provider requires network or credentialing remediation before downstream processing.")

        return ProviderValidationResponse(
            transaction_id=uuid4(),
            npi=npi,
            network_status=network_status,
            credentialing_status=credentialing_status,
            validation_notes=notes,
        )


provider_validation_service = ProviderValidationService()
