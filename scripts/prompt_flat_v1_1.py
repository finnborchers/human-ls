LABEL_GUIDELINES_V1_1 = """
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
- leite die Inhalte nicht aus der Gesamtstimmung oder nur aus der Sternbewertung ab
- vergib ein Label nur, wenn der Text diesen Aspekt klar stützt

Wichtige Abgrenzungen:
- access.waiting nur bei Wartezeiten, Verzögerungen oder langem Warten
- access.reachability nur bei Erreichbarkeit, telefonischem Kontakt oder Terminverfügbarkeit
- access.navigation nur bei Wegfindung, Orientierung oder räumlicher Auffindbarkeit
- communication.information nur, wenn relevante Informationen fehlen oder gegeben werden
- communication.explanation nur, wenn Sachverhalte erklärt oder nicht erklärt werden
- staff.seriousness bei nicht ernst genommen werden, Abwertung oder Bagatellisierung
- care.competence bei wahrgenommener fachlicher Qualität oder fehlender Kompetenz
- care.safety nur bei klaren Hinweisen auf Risiko, Gefährdung, Fehler oder Schaden
- staff.empathy und staff.friendliness als Strength nur bei explizit positivem Textsignal, nicht nur aus allgemeiner Zufriedenheit ableiten

- gib nur die Struktur des Pydantic-Modells zurück
""".strip()


SYSTEM_PROMPT_V1_1 = "You extract structured info and respond only in JSON."


def build_prompt_v1_1(review_text: str) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies nur die Review unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES_V1_1}

Review:
{review_text}
""".strip()
