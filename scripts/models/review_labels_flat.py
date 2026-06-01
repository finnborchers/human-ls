from typing import Literal

from pydantic import BaseModel, Field, field_validator


ReviewLabel = Literal[
    "access.appointments",
    "access.waiting",
    "access.reachability",
    "access.navigation",
    "admin.registration",
    "admin.paperwork",
    "admin.costs",
    "admin.privacy",
    "communication.communication",
    "communication.explanation",
    "communication.information",
    "communication.decisions",
    "staff.friendliness",
    "staff.empathy",
    "staff.respect",
    "staff.seriousness",
    "care.diagnosis",
    "care.treatment",
    "care.medication",
    "care.symptoms",
    "care.safety",
    "care.competence",
    "coordination.coordination",
    "coordination.discharge",
    "coordination.followup",
    "environment.cleanliness",
    "environment.facilities",
    "environment.food",
    "environment.support",
    "inclusion.language",
    "inclusion.interpreting",
    "inclusion.equality",
    "inclusion.culture",
    "inclusion.asylum",
]


class FlatExtraction(BaseModel):
    problem_labels: list[ReviewLabel] = Field(default_factory=list)
    strength_labels: list[ReviewLabel] = Field(default_factory=list)

    @field_validator("problem_labels", "strength_labels")
    @classmethod
    def dedupe_labels(cls, value: list[ReviewLabel]) -> list[ReviewLabel]:
        deduped = []
        seen = set()

        for label in value:
            if label in seen:
                continue

            seen.add(label)
            deduped.append(label)

        return deduped


class FlatReviewMetadata(BaseModel):
    place_id: str | None = None
    clinic_name: str | None = None
    star_rating: int | None = None
    review_time: str | None = None
    like_count: int | None = None
    has_owner_response: bool | None = None


class FlatReviewAnalysisRecord(BaseModel):
    review_id: str
    review_index: int
    metadata: FlatReviewMetadata
    review_text: str
    labels: FlatExtraction
