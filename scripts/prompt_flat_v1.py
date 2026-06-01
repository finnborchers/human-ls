LABEL_GUIDELINES_V1 = """
Extrahiere aus jeder Krankenhausbewertung nur zwei Listen:
- problem_labels
- strength_labels

Es gibt keine weiteren Felder in labels. Nutze nur Labels aus diesem festen Katalog:

access.appointments
access.waiting
access.reachability
access.navigation
admin.registration
admin.paperwork
admin.costs
admin.privacy
communication.communication
communication.explanation
communication.information
communication.decisions
staff.friendliness
staff.empathy
staff.respect
staff.seriousness
care.diagnosis
care.treatment
care.medication
care.symptoms
care.safety
care.competence
coordination.coordination
coordination.discharge
coordination.followup
environment.cleanliness
environment.facilities
environment.food
environment.support
inclusion.language
inclusion.interpreting
inclusion.equality
inclusion.culture
inclusion.asylum

Regeln:
- problem_labels enthält nur negativ oder kritisch beschriebene Aspekte
- strength_labels enthält nur positiv oder lobend beschriebene Aspekte
- verwende nur Labels aus dem Katalog
- verwende keine freien Formulierungen
- ein Label darf in beiden Listen vorkommen, wenn die Review denselben Aspekt sowohl positiv als auch negativ beschreibt
- wenn kein passendes Label vorhanden ist, lasse die Liste leer
- leite die Inhalte nicht nur aus der Sternbewertung ab
- gib nur die Struktur des Pydantic-Modells zurück
""".strip()


SYSTEM_PROMPT_V1 = "You extract structured info and respond only in JSON."


def build_prompt_v1(review_text: str, meta_json: str) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies die Review und die Metadaten unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES_V1}

Metadata:
{meta_json}

Review:
{review_text}
""".strip()
