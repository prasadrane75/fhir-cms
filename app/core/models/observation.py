from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.models.patient import CodeableConcept, Reference


class Quantity(BaseModel):
    value: float | None = None
    unit: str | None = None
    system: str | None = None
    code: str | None = None


class Period(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


class ObservationComponent(BaseModel):
    code: CodeableConcept
    value_quantity: Quantity | None = Field(default=None, alias="valueQuantity")
    value_string: str | None = Field(default=None, alias="valueString")
    interpretation: list[CodeableConcept] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ObservationCreate(BaseModel):
    loinc_code: str = Field(min_length=1, max_length=32)
    display: str = Field(min_length=1, max_length=120)
    value: float
    unit: str = Field(min_length=1, max_length=32)
    effective_date: str | None = None


class Observation(BaseModel):
    """FHIR R4 Observation resource (subset)."""

    resource_type: str = Field(default="Observation", alias="resourceType")
    id: str | None = None
    status: str
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference | None = None
    effective_date_time: datetime | None = Field(default=None, alias="effectiveDateTime")
    effective_period: Period | None = Field(default=None, alias="effectivePeriod")
    issued: datetime | None = None
    performer: list[Reference] = Field(default_factory=list)
    value_quantity: Quantity | None = Field(default=None, alias="valueQuantity")
    value_string: str | None = Field(default=None, alias="valueString")
    value_boolean: bool | None = Field(default=None, alias="valueBoolean")
    interpretation: list[CodeableConcept] = Field(default_factory=list)
    note: list[dict[str, Any]] = Field(default_factory=list)
    component: list[ObservationComponent] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @property
    def display_value(self) -> str:
        if self.value_quantity and self.value_quantity.value is not None:
            unit = self.value_quantity.unit or ""
            return f"{self.value_quantity.value} {unit}".strip()
        if self.value_string:
            return self.value_string
        if self.value_boolean is not None:
            return str(self.value_boolean)
        return "N/A"

    @property
    def code_display(self) -> str:
        return self.code.text or (
            self.code.coding[0].get("display", "Unknown") if self.code.coding else "Unknown"
        )
