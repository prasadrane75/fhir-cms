"""Validate sample FHIR Patient JSON against Pydantic models."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.core.models.patient import Address, HumanName, Identifier, Patient


SAMPLE_PATIENT_JSON = {
    "resourceType": "Patient",
    "id": "example-patient-1",
    "identifier": [
        {
            "use": "official",
            "system": "http://hospital.example.org/patients",
            "value": "MRN-12345",
        }
    ],
    "active": True,
    "name": [
        {
            "use": "official",
            "family": "Doe",
            "given": ["Jane", "Marie"],
            "prefix": ["Ms."],
        }
    ],
    "telecom": [
        {"system": "phone", "value": "555-0100", "use": "home"},
        {"system": "email", "value": "jane.doe@example.com", "use": "work"},
    ],
    "gender": "female",
    "birthDate": "1985-03-15",
    "address": [
        {
            "use": "home",
            "type": "physical",
            "line": ["742 Evergreen Terrace"],
            "city": "Springfield",
            "state": "IL",
            "postalCode": "62704",
            "country": "US",
        }
    ],
    "maritalStatus": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/v3-MaritalStatus",
                "code": "M",
                "display": "Married",
            }
        ],
        "text": "Married",
    },
    "managingOrganization": {
        "reference": "Organization/example-org",
        "display": "Example Hospital",
    },
}


def test_sample_patient_json_validates():
    patient = Patient.model_validate(SAMPLE_PATIENT_JSON)

    assert patient.resource_type == "Patient"
    assert patient.id == "example-patient-1"
    assert patient.active is True
    assert patient.gender == "female"
    assert patient.birth_date == date(1985, 3, 15)


def test_patient_nested_models_parse_correctly():
    patient = Patient.model_validate(SAMPLE_PATIENT_JSON)

    assert len(patient.identifier) == 1
    assert patient.identifier[0] == Identifier(
        use="official",
        system="http://hospital.example.org/patients",
        value="MRN-12345",
    )

    assert patient.name[0] == HumanName(
        use="official",
        family="Doe",
        given=["Jane", "Marie"],
        prefix=["Ms."],
    )

    assert patient.address[0] == Address(
        use="home",
        type="physical",
        line=["742 Evergreen Terrace"],
        city="Springfield",
        state="IL",
        postal_code="62704",
        country="US",
    )


def test_patient_display_name_from_given_and_family():
    patient = Patient.model_validate(SAMPLE_PATIENT_JSON)

    assert patient.display_name == "Jane Marie Doe"


def test_patient_display_name_prefers_name_text():
    payload = {
        "resourceType": "Patient",
        "name": [{"text": "Jane Q. Doe", "family": "Doe", "given": ["Jane"]}],
    }
    patient = Patient.model_validate(payload)

    assert patient.display_name == "Jane Q. Doe"


def test_minimal_patient_json_from_readme_example():
    payload = {
        "resourceType": "Patient",
        "name": [{"family": "Doe", "given": ["Jane"]}],
        "gender": "female",
        "birthDate": "1985-03-15",
    }
    patient = Patient.model_validate(payload)

    assert patient.gender == "female"
    assert patient.birth_date == date(1985, 3, 15)
    assert patient.display_name == "Jane Doe"


def test_patient_rejects_invalid_birth_date():
    payload = {
        "resourceType": "Patient",
        "birthDate": "not-a-date",
    }

    with pytest.raises(ValidationError):
        Patient.model_validate(payload)


def test_patient_rejects_invalid_active_flag():
    payload = {
        "resourceType": "Patient",
        "active": {"status": "yes"},
    }

    with pytest.raises(ValidationError):
        Patient.model_validate(payload)
