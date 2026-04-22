#!/usr/bin/env python3

import json
import os
import time

from dotenv import load_dotenv
from instructor import from_openai
from openai import OpenAI
from pydantic import BaseModel, Field


# ========== Setup ==========
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = from_openai(OpenAI(api_key=OPENAI_API_KEY))

ARTIFACTS_ROOT = "artifacts"
CAPTURE_SUMMARY_PATH = "artifacts/capture_reviews_run_summary.json"
OUT_PATH = "analysis/review_label_results_v1.json"
MODEL = "gpt-5-nano"
START_INDEX = 0
NUM_REVIEWS = 20

os.makedirs("analysis", exist_ok=True)


# ========== Pydantic Models ==========
class AccessAndTimeLabels(BaseModel):
    long_wait_time: bool | None = Field(..., description="Lengthy waiting for care after arrival, triage, or check-in.")
    appointment_delay: bool | None = Field(..., description="Long lead time before an appointment, consultation, or procedure.")
    same_day_delay: bool | None = Field(..., description="Substantial delay on the day of appointment or treatment.")
    rescheduling_cancellation: bool | None = Field(..., description="Appointment, operation, or treatment moved, postponed, or canceled.")


class FrontDeskAndAdminLabels(BaseModel):
    registration_problem: bool | None = Field(..., description="Problems at reception, check-in, registration, or intake.")
    phone_unreachable: bool | None = Field(..., description="Unanswered calls, unreachable departments, or missing callbacks.")
    paperwork_document_issue: bool | None = Field(..., description="Missing, incorrect, delayed, or mishandled paperwork.")
    billing_cost_issue: bool | None = Field(..., description="Unexpected costs, billing disputes, or unclear charges.")
    referral_or_authorization_issue: bool | None = Field(..., description="Friction around referrals, transfers, or required approvals.")


class CommunicationAndRespectLabels(BaseModel):
    rude_tone: bool | None = Field(..., description="Rude, hostile, insulting, or disrespectful tone.")
    not_taken_seriously: bool | None = Field(..., description="Patient or family felt dismissed, ignored, or not believed.")
    poor_explanation: bool | None = Field(..., description="Insufficient explanation of diagnosis, treatment, process, or next steps.")
    lack_of_empathy: bool | None = Field(..., description="Low compassion, emotional coldness, or lack of understanding.")
    staff_conflict_or_blame: bool | None = Field(..., description="Staff argued, blamed patient/family, or escalated conflict.")


class ClinicalCareAndSafetyLabels(BaseModel):
    missed_or_wrong_diagnosis: bool | None = Field(..., description="Diagnosis missed, delayed, incorrect, or later contradicted.")
    treatment_delay_or_denial: bool | None = Field(..., description="Needed treatment delayed, withheld, refused, or not meaningfully provided.")
    procedure_or_surgery_issue: bool | None = Field(..., description="Problem with a procedure, surgery, intervention, or technical execution.")
    medication_issue: bool | None = Field(..., description="Wrong, missing, harmful, or badly managed medication.")
    safety_incident: bool | None = Field(..., description="Concrete safety failure, harmful event, or serious preventable risk.")


class PainAndSymptomResponseLabels(BaseModel):
    pain_not_managed: bool | None = Field(..., description="Significant pain untreated, undertreated, or responded to too slowly.")
    symptoms_not_responded_to: bool | None = Field(..., description="Urgent or worsening symptoms did not receive timely attention.")
    mobility_or_basic_help_missing: bool | None = Field(..., description="Missing help with mobility, toilet use, hydration, feeding, or basic support.")


class DischargeAndFollowUpLabels(BaseModel):
    premature_discharge: bool | None = Field(..., description="Discharge happened too early despite unresolved concerns.")
    bad_discharge_instructions: bool | None = Field(..., description="Discharge instructions were unclear, missing, or inadequate.")
    missing_or_wrong_discharge_documents: bool | None = Field(..., description="Discharge letters, prescriptions, or summaries missing, delayed, or wrong.")
    followup_coordination_problem: bool | None = Field(..., description="Poor coordination of aftercare, referrals, follow-ups, or continuity.")


class EnvironmentAndComfortLabels(BaseModel):
    hygiene_cleanliness_issue: bool | None = Field(..., description="Dirty, unhygienic, or visibly unsanitary conditions.")
    room_or_bed_issue: bool | None = Field(..., description="Room setup, bed availability, or accommodation problems.")
    food_quality_issue: bool | None = Field(..., description="Poor, missing, unsuitable, or badly managed food/drink provision.")
    noise_privacy_issue: bool | None = Field(..., description="Lack of privacy, excessive noise, or compromised dignity.")
    parking_or_accessory_facility_issue: bool | None = Field(..., description="Parking, wifi, signage, or waiting-area related friction.")


class LanguageAndInclusionLabels(BaseModel):
    language_barrier: bool | None = Field(..., description="Communication problems caused by language mismatch.")
    missing_translation_support: bool | None = Field(..., description="Missing interpreter or translation support.")
    migrant_discrimination: bool | None = Field(..., description="Explicit discrimination linked to migration, ethnicity, religion, or foreignness.")
    xenophobic_staff_complaint: bool | None = Field(..., description="Review contains xenophobic complaints about foreign staff/accents.")


class FamilyAndCaregiverExperienceLabels(BaseModel):
    family_not_informed: bool | None = Field(..., description="Family/caregivers did not receive needed updates.")
    companion_or_visitation_problem: bool | None = Field(..., description="Friction around accompaniment, visitation, or family presence.")
    caregiver_support_missing: bool | None = Field(..., description="Caregivers/relatives lacked needed support or orientation.")


class Extraction(BaseModel):
    access_and_time: AccessAndTimeLabels
    front_desk_and_admin: FrontDeskAndAdminLabels
    communication_and_respect: CommunicationAndRespectLabels
    clinical_care_and_safety: ClinicalCareAndSafetyLabels
    pain_and_symptom_response: PainAndSymptomResponseLabels
    discharge_and_follow_up: DischargeAndFollowUpLabels
    environment_and_comfort: EnvironmentAndComfortLabels
    language_and_inclusion: LanguageAndInclusionLabels
    family_and_caregiver_experience: FamilyAndCaregiverExperienceLabels


class ReviewMetadata(BaseModel):
    place_id: str | None = None
    clinic_name: str | None = None
    reviewer_name: str | None = None
    star_rating: int | None = None
    review_time: str | None = None


class ReviewAnalysisRecord(BaseModel):
    review_id: str
    review_index: int
    metadata: ReviewMetadata
    review_text: str
    labels: Extraction


LABEL_GUIDELINES = """
Access and Time (access_and_time):
- long_wait_time: Lengthy waiting for care after arrival, triage, or check-in.
- appointment_delay: Long lead time before an appointment, consultation, or procedure.
- same_day_delay: Substantial delay on the day of appointment or treatment.
- rescheduling_cancellation: Appointment, operation, or treatment moved, postponed, or canceled.

Front Desk and Admin (front_desk_and_admin):
- registration_problem: Problems at reception, check-in, registration, or intake.
- phone_unreachable: Unanswered calls, unreachable departments, or missing callbacks.
- paperwork_document_issue: Missing, incorrect, delayed, or mishandled paperwork.
- billing_cost_issue: Unexpected costs, billing disputes, or unclear charges.
- referral_or_authorization_issue: Friction around referrals, transfers, or required approvals.

Communication and Respect (communication_and_respect):
- rude_tone: Rude, hostile, insulting, or disrespectful tone.
- not_taken_seriously: Patient or family felt dismissed, ignored, or not believed.
- poor_explanation: Insufficient explanation of diagnosis, treatment, process, or next steps.
- lack_of_empathy: Low compassion, emotional coldness, or lack of understanding.
- staff_conflict_or_blame: Staff argued, blamed patient/family, or escalated conflict.

Clinical Care and Safety (clinical_care_and_safety):
- missed_or_wrong_diagnosis: Diagnosis missed, delayed, incorrect, or later contradicted.
- treatment_delay_or_denial: Needed treatment delayed, withheld, refused, or not meaningfully provided.
- procedure_or_surgery_issue: Problem with a procedure, surgery, intervention, or technical execution.
- medication_issue: Wrong, missing, harmful, or badly managed medication.
- safety_incident: Concrete safety failure, harmful event, or serious preventable risk.

Pain and Symptom Response (pain_and_symptom_response):
- pain_not_managed: Significant pain untreated, undertreated, or responded to too slowly.
- symptoms_not_responded_to: Urgent or worsening symptoms did not receive timely attention.
- mobility_or_basic_help_missing: Missing help with mobility, toilet use, hydration, feeding, or basic support.

Discharge and Follow-up (discharge_and_follow_up):
- premature_discharge: Discharge happened too early despite unresolved concerns.
- bad_discharge_instructions: Discharge instructions were unclear, missing, or inadequate.
- missing_or_wrong_discharge_documents: Discharge letters, prescriptions, or summaries missing, delayed, or wrong.
- followup_coordination_problem: Poor coordination of aftercare, referrals, follow-ups, or continuity.

Environment and Comfort (environment_and_comfort):
- hygiene_cleanliness_issue: Dirty, unhygienic, or visibly unsanitary conditions.
- room_or_bed_issue: Room setup, bed availability, or accommodation problems.
- food_quality_issue: Poor, missing, unsuitable, or badly managed food/drink provision.
- noise_privacy_issue: Lack of privacy, excessive noise, or compromised dignity.
- parking_or_accessory_facility_issue: Parking, wifi, signage, or waiting-area related friction.

Language and Inclusion (language_and_inclusion):
- language_barrier: Communication problems caused by language mismatch.
- missing_translation_support: Missing interpreter or translation support.
- migrant_discrimination: Explicit discrimination linked to migration, ethnicity, religion, or foreignness.
- xenophobic_staff_complaint: Review contains xenophobic complaints about foreign staff/accents.

Family and Caregiver Experience (family_and_caregiver_experience):
- family_not_informed: Family/caregivers did not receive needed updates.
- companion_or_visitation_problem: Friction around accompaniment, visitation, or family presence.
- caregiver_support_missing: Caregivers/relatives lacked needed support or orientation.
""".strip()


# ========== Prompt ==========
def build_prompt(review_text: str, meta: dict) -> str:
    return f"""
You are an expert information extraction model for hospital reviews.
Read the review and metadata below.
Fill the Pydantic response model fields exactly as defined.

For every label:
- true: problem clearly present
- false: problem clearly not present
- null: not enough information or ambiguous

Only problem-focused labels should be triggered.
Do not mark positive comments as problems.

Labels:
{LABEL_GUIDELINES}

Metadata:
{json.dumps(meta, ensure_ascii=False, indent=2)}

Review:
{review_text}
""".strip()


# ========== Load Data ==========
place_names = {}
if os.path.exists(CAPTURE_SUMMARY_PATH):
    with open(CAPTURE_SUMMARY_PATH, "r", encoding="utf-8") as f:
        summary = json.load(f)

    for place in summary.get("places", []):
        place_id = place.get("place_id")
        place_name = place.get("place_name")
        if place_id and place_name:
            place_names[place_id] = place_name

records = []
for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
    reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
    if not os.path.exists(reviews_path):
        continue

    with open(reviews_path, "r", encoding="utf-8") as f:
        reviews = json.load(f)

    for review_index, review in enumerate(reviews):
        records.append(
            {
                "review_id": f"{place_id}:{review_index}",
                "place_id": place_id,
                "clinic_name": place_names.get(place_id),
                "review_index": review_index,
                "reviewer_name": review.get("reviewer_name"),
                "star_rating": review.get("star_rating"),
                "review_time": review.get("review_time"),
                "review_text": review.get("review_text", ""),
            }
        )

records = records[START_INDEX : START_INDEX + NUM_REVIEWS]


# ========== Load existing results ==========
if os.path.exists(OUT_PATH):
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = {}


# ========== Time Tracking ==========
t_total_start = time.time()
processed = 0
total_request_sec = 0.0
skipped = 0
errors = 0


# ========== Process ==========
for row in records:
    review_id = row["review_id"]
    if review_id in results:
        skipped += 1
        print(f"[skip] review_id={review_id} already done.")
        continue

    review_text = row.get("review_text", "")
    if not review_text.strip():
        skipped += 1
        print(f"[skip] review_id={review_id} has empty text.")
        continue

    meta = {
        "place_id": row.get("place_id"),
        "clinic_name": row.get("clinic_name"),
        "reviewer_name": row.get("reviewer_name"),
        "star_rating": row.get("star_rating"),
        "review_time": row.get("review_time"),
    }

    prompt = build_prompt(review_text, meta)

    try:
        t_req_start = time.time()
        extraction = client.chat.completions.create(
            model=MODEL,
            response_model=Extraction,
            messages=[
                {"role": "system", "content": "You extract structured info and respond only in JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        t_req = time.time() - t_req_start

        record = ReviewAnalysisRecord(
            review_id=review_id,
            review_index=row["review_index"],
            metadata=ReviewMetadata(**meta),
            review_text=review_text,
            labels=extraction,
        )
        results[review_id] = record.model_dump()

        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        processed += 1
        total_request_sec += t_req
        print(f"[ok] review_id={review_id} | {t_req:.2f}s")

    except Exception as e:
        errors += 1
        print(f"[error] review_id={review_id}: {e}")


# ========== Summary ==========
t_total = time.time() - t_total_start
avg_per_review = (total_request_sec / processed) if processed > 0 else 0.0
per_min = (60.0 / avg_per_review) if avg_per_review > 0 else 0.0

print("\n=== SUMMARY ===")
print(f"Processed: {processed}")
print(f"Skipped:   {skipped}")
print(f"Errors:    {errors}")
print(f"Total wall-clock: {t_total:.2f}s")
print(f"Avg request time/review: {avg_per_review:.2f}s")
print(f"Throughput: ~{per_min:.1f} reviews/min (model time)")
print(f"Output: {OUT_PATH}")