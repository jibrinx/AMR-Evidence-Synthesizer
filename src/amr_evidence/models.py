"""Scientific data contracts shared by UI, storage, and agent tools."""

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Outcome = Literal["resistant", "non_susceptible", "intermediate", "unknown"]
Status = Literal["pending", "approved", "rejected"]
DOMAINS = (
    "sampling",
    "population",
    "ast_breakpoints",
    "denominator",
    "isolate_deduplication",
    "interpretation",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class Study(Contract):
    title: str = Field(min_length=1, max_length=2000)
    pmid: str | None = Field(default=None, pattern=r"^\d{1,12}$")
    doi: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1800, le=2200)
    authors: str | None = Field(default=None, max_length=4000)
    journal: str | None = Field(default=None, max_length=1000)

    @field_validator("doi", mode="before")
    @classmethod
    def clean_doi(cls, value):
        if not value:
            return None
        value = value.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            value = value.removeprefix(prefix).strip()
        if not value.startswith("10.") or "/" not in value:
            raise ValueError("DOI must start with 10. and contain a slash.")
        return value


class Estimate(Contract):
    source_id: StrictInt = Field(gt=0)
    page: StrictInt = Field(ge=1)
    quote: str = Field(min_length=1, max_length=8000)
    organism_raw: str | None = Field(default=None, max_length=300)
    organism_normalized: str | None = Field(default=None, max_length=300)
    antibiotic_raw: str | None = Field(default=None, max_length=300)
    antibiotic_normalized: str | None = Field(default=None, max_length=300)
    outcome: Outcome = "unknown"
    mapping_uncertain: bool = Field(default=False, strict=True)
    numerator: StrictInt | None = Field(default=None, ge=0, le=1_000_000_000)
    denominator: StrictInt | None = Field(default=None, gt=0, le=1_000_000_000)
    reported_percentage: str | None = Field(default=None, max_length=30)
    sampling_unit: str | None = Field(default=None, max_length=300)
    stratum: str | None = Field(default=None, max_length=1000)
    country: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=1000)
    setting: str | None = Field(default=None, max_length=1000)
    collection_dates: str | None = Field(default=None, max_length=300)
    sector: Literal["human", "animal", "environmental", "mixed", "unknown"] = "unknown"
    specimen: str | None = Field(default=None, max_length=1000)
    ast_method: str | None = Field(default=None, max_length=1000)
    breakpoint_standard: str | None = Field(default=None, max_length=300)
    breakpoint_version: str | None = Field(default=None, max_length=300)
    reported_ci: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)
    ai_observations: str | None = Field(default=None, max_length=4000)

    @field_validator("*", mode="before")
    @classmethod
    def null_empty(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("reported_percentage")
    @classmethod
    def percentage(cls, value):
        if value is None:
            return None
        # Decimal precision is retained for the consistency/rounding check.
        import re

        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,8})?", value):
            raise ValueError("Use a reported numeric percentage, e.g. 42.5, without %.")
        try:
            if not Decimal(0) <= Decimal(value) <= Decimal(100):
                raise ValueError("Percentage must be between 0 and 100.")
        except InvalidOperation as exc:
            raise ValueError("Invalid percentage.") from exc
        return value

    @model_validator(mode="after")
    def counts(self):
        if (
            self.numerator is not None
            and self.denominator is not None
            and self.numerator > self.denominator
        ):
            raise ValueError("Numerator cannot exceed the tested denominator.")
        return self

    def flags(self) -> list[str]:
        flags = []
        for key in (
            "organism_raw",
            "antibiotic_raw",
            "denominator",
            "sampling_unit",
            "ast_method",
            "breakpoint_standard",
            "breakpoint_version",
            "collection_dates",
        ):
            if getattr(self, key) is None:
                flags.append(f"missing_{key}")
        if self.outcome == "unknown":
            flags.append("undefined_outcome")
        if self.mapping_uncertain:
            flags.append("ambiguous_entity_or_stratum_mapping")
        if self.sector == "unknown":
            flags.append("unknown_sector")
        if (
            self.numerator is not None
            and self.denominator is not None
            and self.reported_percentage is not None
        ):
            reported = Decimal(self.reported_percentage)
            half_unit = Decimal(5).scaleb(reported.as_tuple().exponent - 1)
            calculated = Decimal(100) * self.numerator / self.denominator
            if abs(calculated - reported) > half_unit + Decimal("0.000000001"):
                flags.append("count_percentage_inconsistency")
        return flags


class DomainAssessment(Contract):
    judgment: Literal["not_assessed", "low_concern", "some_concern", "high_concern", "unclear"]
    rationale: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def explain(self):
        if self.judgment != "not_assessed" and not self.rationale:
            raise ValueError("A quality judgment requires a rationale.")
        return self


class Review(Contract):
    reviewer: str = Field(min_length=1, max_length=200)
    status: Status = "pending"
    nigeria_eligible: bool = False
    rationale: str = Field(default="", max_length=4000)
    assessments: dict[str, DomainAssessment] = Field(default_factory=dict)

    @field_validator("assessments")
    @classmethod
    def domains(cls, value):
        if set(value) - set(DOMAINS):
            raise ValueError("Unknown assessment domain.")
        return value

    def check_approval(self, estimate: Estimate):
        if self.status != "approved":
            return
        if not self.nigeria_eligible:
            raise ValueError("Human confirmation of Nigeria eligibility is required.")
        if estimate.mapping_uncertain:
            raise ValueError("Resolve ambiguous organism/drug/stratum mapping before approval.")
        if (
            not estimate.organism_raw
            or not estimate.antibiotic_raw
            or estimate.outcome == "unknown"
        ):
            raise ValueError("Approval requires organism, antibiotic, and defined outcome.")
        if estimate.reported_percentage is None and (
            estimate.numerator is None or estimate.denominator is None
        ):
            raise ValueError("Approval requires a reported percentage or a complete count pair.")
        if "count_percentage_inconsistency" in estimate.flags():
            raise ValueError("Resolve inconsistent counts/percentage before approval.")
