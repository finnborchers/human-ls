from pydantic import BaseModel, Field, model_validator


class AccessLabels(BaseModel):
    appointments: bool | None = Field(None, description="Appointment-related aspect.")
    waiting: bool | None = Field(None, description="Waiting-time-related aspect.")
    reachability: bool | None = Field(None, description="Reachability-related aspect.")
    navigation: bool | None = Field(None, description="Navigation or wayfinding-related aspect.")


class AdminLabels(BaseModel):
    registration: bool | None = Field(None, description="Registration or admission-related aspect.")
    paperwork: bool | None = Field(None, description="Paperwork or documentation-related aspect.")
    costs: bool | None = Field(None, description="Cost or insurance-related aspect.")
    privacy: bool | None = Field(None, description="Privacy or confidentiality-related aspect.")


class CommunicationLabels(BaseModel):
    communication: bool | None = Field(None, description="General communication-related aspect.")
    explanation: bool | None = Field(None, description="Explanation or clarification-related aspect.")
    information: bool | None = Field(None, description="Information or update-related aspect.")
    decisions: bool | None = Field(None, description="Decision-making or involvement-related aspect.")


class StaffLabels(BaseModel):
    friendliness: bool | None = Field(None, description="Friendliness-related aspect.")
    empathy: bool | None = Field(None, description="Empathy-related aspect.")
    respect: bool | None = Field(None, description="Respect-related aspect.")
    seriousness: bool | None = Field(None, description="Being taken seriously-related aspect.")


class CareLabels(BaseModel):
    diagnosis: bool | None = Field(None, description="Diagnosis-related aspect.")
    treatment: bool | None = Field(None, description="Treatment-related aspect.")
    medication: bool | None = Field(None, description="Medication-related aspect.")
    symptoms: bool | None = Field(None, description="Pain or symptom-management-related aspect.")
    safety: bool | None = Field(None, description="Safety-related aspect.")
    competence: bool | None = Field(None, description="Clinical or professional competence-related aspect.")


class CoordinationLabels(BaseModel):
    coordination: bool | None = Field(None, description="Internal coordination-related aspect.")
    discharge: bool | None = Field(None, description="Discharge-related aspect.")
    followup: bool | None = Field(None, description="Follow-up or continuity-related aspect.")


class EnvironmentLabels(BaseModel):
    cleanliness: bool | None = Field(None, description="Cleanliness or hygiene-related aspect.")
    facilities: bool | None = Field(None, description="Facilities or physical environment-related aspect.")
    food: bool | None = Field(None, description="Food or catering-related aspect.")
    support: bool | None = Field(None, description="Basic support or daily care-related aspect.")


class InclusionLabels(BaseModel):
    language: bool | None = Field(None, description="Language-related aspect.")
    interpreting: bool | None = Field(None, description="Interpreting or translation-related aspect.")
    equality: bool | None = Field(None, description="Equality, discrimination, or racism-related aspect.")
    culture: bool | None = Field(None, description="Cultural or religious needs-related aspect.")
    asylum: bool | None = Field(None, description="Refugee, flight, or asylum-related aspect.")


class Problems(BaseModel):
    access: AccessLabels = Field(default_factory=AccessLabels)
    admin: AdminLabels = Field(default_factory=AdminLabels)
    communication: CommunicationLabels = Field(default_factory=CommunicationLabels)
    staff: StaffLabels = Field(default_factory=StaffLabels)
    care: CareLabels = Field(default_factory=CareLabels)
    coordination: CoordinationLabels = Field(default_factory=CoordinationLabels)
    environment: EnvironmentLabels = Field(default_factory=EnvironmentLabels)
    inclusion: InclusionLabels = Field(default_factory=InclusionLabels)

    @model_validator(mode="before")
    @classmethod
    def replace_null_blocks(cls, data):
        if not isinstance(data, dict):
            return data

        for key in ["access", "admin", "communication", "staff", "care", "coordination", "environment", "inclusion"]:
            if data.get(key) is None:
                data[key] = {}

        return data


class Strengths(BaseModel):
    access: AccessLabels = Field(default_factory=AccessLabels)
    admin: AdminLabels = Field(default_factory=AdminLabels)
    communication: CommunicationLabels = Field(default_factory=CommunicationLabels)
    staff: StaffLabels = Field(default_factory=StaffLabels)
    care: CareLabels = Field(default_factory=CareLabels)
    coordination: CoordinationLabels = Field(default_factory=CoordinationLabels)
    environment: EnvironmentLabels = Field(default_factory=EnvironmentLabels)
    inclusion: InclusionLabels = Field(default_factory=InclusionLabels)

    @model_validator(mode="before")
    @classmethod
    def replace_null_blocks(cls, data):
        if not isinstance(data, dict):
            return data

        for key in ["access", "admin", "communication", "staff", "care", "coordination", "environment", "inclusion"]:
            if data.get(key) is None:
                data[key] = {}

        return data


class Extraction(BaseModel):
    overall_sentiment: str = Field("unclear", description="negative, mixed, neutral, positive, or unclear.")
    care_context: list[str] = Field(
        default_factory=list,
        description="Short context tags such as emergency, outpatient, ward, surgery, maternity, pediatrics, psychiatry, intensive_care, admin, or unknown.",
    )
    problem_labels: list[str] = Field(default_factory=list, description="Most important negative labels using canonical dot paths.")
    strength_labels: list[str] = Field(default_factory=list, description="Most important positive labels using canonical dot paths.")
    problems: Problems = Field(default_factory=Problems)
    strengths: Strengths = Field(default_factory=Strengths)
    evidence_spans: list[str] = Field(default_factory=list, description="Up to five short excerpts from the review that support the main labels.")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class ReviewMetadata(BaseModel):
    place_id: str | None = None
    clinic_name: str | None = None
    star_rating: int | None = None
    review_time: str | None = None
    like_count: int | None = None
    has_owner_response: bool | None = None


class ReviewAnalysisRecord(BaseModel):
    review_id: str
    review_index: int
    metadata: ReviewMetadata
    review_text: str
    labels: Extraction
