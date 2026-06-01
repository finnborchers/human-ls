#!/usr/bin/env python3

import json
import os
import time

from dotenv import load_dotenv
from instructor import from_openai
from scripts.models.review_labels_nested import Extraction, ReviewAnalysisRecord, ReviewMetadata
from openai import OpenAI


# ========== Setup ==========
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found in .env")

client = from_openai(OpenAI(api_key=OPENAI_API_KEY))

ARTIFACTS_ROOT = "artifacts"
OUT_PATH = os.getenv("REVIEW_LABELS_OUT_PATH", "analysis/llm/full_run/review_labels_latest.json")
MODEL = os.getenv("REVIEW_LABELS_MODEL", "gpt-4.1-mini")
START_INDEX = int(os.getenv("REVIEW_LABELS_START_INDEX", "0"))
NUM_REVIEWS = int(os.getenv("REVIEW_LABELS_NUM_REVIEWS", "20"))
SAMPLE_PATH = os.getenv("REVIEW_LABELS_SAMPLE_PATH")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)


LABEL_GUIDELINES = """
Nutze die Taxonomie unten, um Probleme und Stärken getrennt zu extrahieren.
Die Struktur ist vollständig gespiegelt: problems und strengths verwenden dieselben Domänen und dieselben Feldnamen.
Eine Review kann in derselben Domäne gleichzeitig Probleme und Stärken enthalten.

Wichtige Grundlogik:
- problems beschreibt nur negative, kritische oder barriererelevante Aussagen
- strengths beschreibt nur positive, hilfreiche oder lobende Aussagen
- beide Blöcke müssen immer vollständig vorhanden sein
- wenn eine Aussage klar positiv ist, gehört sie nicht in problems
- wenn eine Aussage klar negativ ist, gehört sie nicht in strengths
- wenn zu einer Domäne nichts Relevantes gesagt wird, setze die Felder auf null
- nutze false nur, wenn aus dem Text klar hervorgeht, dass das Gegenteil zutrifft
- nutze problem_labels nur für Felder in problems mit true
- nutze strength_labels nur für Felder in strengths mit true
- verwende als Labelpfade genau: domain.field

Arbeite gedanklich in dieser Reihenfolge:
1. Welche Textstellen sind klar negativ?
2. Welche Textstellen sind klar positiv?
3. Weise negative Textstellen problems zu.
4. Weise positive Textstellen strengths zu.
5. Prüfe, dass problems und strengths beide vorhanden sind.

Domäne access:
- appointments: alles rund um Terminvergabe, Terminabsage, Terminverschiebung oder fehlende Termine
- waiting: Wartezeit vor Untersuchung, Behandlung, Aufnahme oder Entlassung
- reachability: Erreichbarkeit per Telefon, E-Mail oder Rückruf
- navigation: Wegfindung, Beschilderung, Zugang oder Orientierung vor Ort

Domäne admin:
- registration: Anmeldung, Aufnahme, Empfang, Check-in
- paperwork: Befunde, Briefe, Rezepte, Formulare, Berichte, Unterlagen
- costs: Versicherung, Kosten, Abrechnung, Zahlung
- privacy: Datenschutz, Schweigepflicht, Vertraulichkeit

Domäne communication:
- communication: allgemeine Kommunikation
- explanation: Erklärung oder Aufklärung
- information: Informationen oder Updates für Patientinnen, Patienten oder Angehörige
- decisions: Einbeziehung in Entscheidungen oder Einwilligung

Domäne staff:
- friendliness: freundlich vs. unfreundlich
- empathy: einfühlsam vs. kalt/gleichgültig
- respect: respektvoll vs. respektlos/herablassend
- seriousness: ernst genommen vs. nicht ernst genommen

Domäne care:
- diagnosis: Diagnose
- treatment: Behandlung, Eingriff, Therapie, Versorgung
- medication: Medikamente oder Medikation
- symptoms: Schmerzen, Beschwerden oder Symptommanagement
- safety: Gefährdung, Fehler, Sicherheitsaspekt
- competence: fachliche Kompetenz

Domäne coordination:
- coordination: Abstimmung zwischen Stationen, Abteilungen oder Berufsgruppen
- discharge: Entlassung, Entlassunterlagen, Entlassorganisation
- followup: Nachsorge, Anschlussbehandlung, Überleitung, Weiterbehandlung

Domäne environment:
- cleanliness: Sauberkeit oder Hygiene
- facilities: Zimmer, Wartebereich, Toiletten, Ausstattung, Parken
- food: Essen, Getränke, Verpflegung
- support: Grundpflege, Mobilitätshilfe, Hilfe im Alltag

Domäne inclusion:
- language: sprachliche Verständigungsprobleme oder gute sprachliche Verständigung
- interpreting: Dolmetschen, Übersetzung oder deren Fehlen
- equality: Gleichbehandlung vs. Diskriminierung/Rassismus
- culture: kulturelle oder religiöse Bedürfnisse
- asylum: expliziter Bezug zu Flucht oder Asyl

Beispiele für strengths:
- strengths.staff.friendliness: freundlich, nett, herzlich, hilfsbereit
- strengths.staff.empathy: einfühlsam, fürsorglich, liebevoll, zugewandt
- strengths.staff.respect: respektvoll, wertschätzend
- strengths.staff.seriousness: ernst genommen, aufmerksam zugehört
- strengths.care.treatment: gute Behandlung, erfolgreiche OP, hilfreiche Therapie
- strengths.care.competence: kompetent, fachlich stark, professionell
- strengths.access.waiting: ausdrücklich kurze oder sehr gute Wartezeit
- strengths.communication.explanation: verständlich erklärt, gut aufgeklärt
- strengths.communication.information: gut informiert, Rückruf erhalten, aktiv informiert
- strengths.environment.cleanliness: sauber, hygienisch, gepflegt
- strengths.environment.food: gutes Essen, gute Verpflegung
- strengths.environment.support: gute Unterstützung im Alltag oder in der Pflege

Beispiele für problems:
- problems.staff.friendliness: unfreundlich, patzig, arrogant
- problems.staff.empathy: kalt, gleichgültig, wenig einfühlsam
- problems.staff.respect: respektlos, herablassend
- problems.staff.seriousness: nicht ernst genommen, abgewimmelt
- problems.care.treatment: Behandlung unzureichend, schlecht oder verspätet
- problems.care.competence: inkompetent, fachlich schwach
- problems.access.waiting: lange Wartezeit
- problems.communication.explanation: unzureichend erklärt
- problems.communication.information: nicht informiert
- problems.environment.cleanliness: unhygienisch, schmutzig
- problems.environment.food: schlechtes Essen
- problems.environment.support: fehlende Hilfe im Alltag oder in der Pflege

Regeln:
- true: klar vorhanden
- false: klar nicht vorhanden
- null: unklar oder nicht genug Information
- problems und strengths sind getrennt zu füllen
- dieselben Felder dürfen in beiden Blöcken true sein, wenn eine Review gemischte Aussagen enthält
- verwende problem_labels und strength_labels als kanonische Punktpfade, zum Beispiel access.waiting oder care.treatment
- schließe nicht allein aus der Sternbewertung auf die Inhalte
- schließe keinen Flucht- oder Asylbezug aus Namen oder Herkunftsvermutungen
- evidence_spans sollen kurze direkte Textausschnitte aus der Review sein

Erwarte immer diese Grundstruktur:
- overall_sentiment
- care_context
- problem_labels
- strength_labels
- problems mit access, admin, communication, staff, care, coordination, environment, inclusion
- strengths mit access, admin, communication, staff, care, coordination, environment, inclusion
- evidence_spans
- confidence
""".strip()


# ========== Prompt ==========
def build_prompt(review_text: str, meta: dict) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies die Review und die Metadaten unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES}

Metadata:
{json.dumps(meta, ensure_ascii=False, indent=2)}

Review:
{review_text}
""".strip()


def collect_true_paths(block: dict, prefix: str = "") -> list[str]:
    paths = []

    for key, value in block.items():
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            paths.extend(collect_true_paths(value, path))
        elif value is True:
            paths.append(path)

    return paths


# ========== Load Data ==========
records = []
for place_id in sorted(os.listdir(ARTIFACTS_ROOT)):
    reviews_path = os.path.join(ARTIFACTS_ROOT, place_id, "reviews.json")
    if not os.path.exists(reviews_path):
        continue

    try:
        with open(reviews_path, "r", encoding="utf-8") as f:
            reviews = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[warn] skipping unreadable file, probably still being written: {reviews_path} ({e})")
        continue

    for review_index, review in enumerate(reviews):
        records.append(
            {
                "review_id": f"{place_id}:{review_index}",
                "place_id": place_id,
                "clinic_name": None,
                "review_index": review_index,
                "star_rating": review.get("star_rating"),
                "review_time": review.get("review_time"),
                "like_count": review.get("like_count"),
                "has_owner_response": review.get("has_owner_response"),
                "review_text": review.get("review_text", ""),
            }
        )

if SAMPLE_PATH:
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        sample_ids = {line.strip() for line in f if line.strip()}

    records = [row for row in records if row["review_id"] in sample_ids]

records = records[START_INDEX : START_INDEX + NUM_REVIEWS]


# ========== Load Existing Results ==========
if os.path.exists(OUT_PATH):
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)
else:
    results = {}


# ========== Process ==========
t_total_start = time.time()
processed = 0
total_request_sec = 0.0
skipped = 0
errors = 0

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
        "star_rating": row.get("star_rating"),
        "review_time": row.get("review_time"),
        "like_count": row.get("like_count"),
        "has_owner_response": row.get("has_owner_response"),
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

        extraction.problem_labels = collect_true_paths(extraction.problems.model_dump())
        extraction.strength_labels = collect_true_paths(extraction.strengths.model_dump())

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
