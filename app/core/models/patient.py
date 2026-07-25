from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class Identifier(BaseModel):
    system: str | None = None
    value: str | None = None
    use: str | None = None


class HumanName(BaseModel):
    use: str | None = None
    family: str | None = None
    given: list[str] = Field(default_factory=list)
    prefix: list[str] = Field(default_factory=list)
    suffix: list[str] = Field(default_factory=list)
    text: str | None = None


class ContactPoint(BaseModel):
    system: str | None = None
    value: str | None = None
    use: str | None = None


class Address(BaseModel):
    use: str | None = None
    type: str | None = None
    line: list[str] = Field(default_factory=list)
    city: str | None = None
    state: str | None = None
    postal_code: str | None = Field(default=None, alias="postalCode")
    country: str | None = None

    model_config = {"populate_by_name": True}


class CodeableConcept(BaseModel):
    coding: list[dict[str, Any]] = Field(default_factory=list)
    text: str | None = None


class Reference(BaseModel):
    reference: str | None = None
    type: str | None = None
    display: str | None = None


class Patient(BaseModel):
    """FHIR R4 Patient resource (subset)."""

    resource_type: str = Field(default="Patient", alias="resourceType")
    id: str | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    active: bool | None = True
    name: list[HumanName] = Field(default_factory=list)
    telecom: list[ContactPoint] = Field(default_factory=list)
    gender: str | None = None
    birth_date: date | None = Field(default=None, alias="birthDate")
    address: list[Address] = Field(default_factory=list)
    marital_status: CodeableConcept | None = Field(default=None, alias="maritalStatus")
    managing_organization: Reference | None = Field(default=None, alias="managingOrganization")

    model_config = {"populate_by_name": True}

    @property
    def display_name(self) -> str:
        if self.name and self.name[0].text:
            return self.name[0].text
        if self.name and (self.name[0].given or self.name[0].family):
            parts = self.name[0].given + ([self.name[0].family] if self.name[0].family else [])
            return " ".join(parts)
        return self.id or "Unknown Patient"
