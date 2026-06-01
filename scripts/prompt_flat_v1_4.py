from prompt_flat_v1 import LABEL_GUIDELINES_V1, SYSTEM_PROMPT_V1


LABEL_GUIDELINES_V1_4 = (
    LABEL_GUIDELINES_V1
    + "\n\n"
    + """
Gezielte Klarstellungen:
- access.waiting bei Wartezeiten, Verzögerungen oder langem Warten
- access.reachability bei telefonischer Erreichbarkeit, Kontaktaufnahme oder Terminverfügbarkeit
- communication.information wenn Informationen fehlen, nicht gegeben werden oder unklar bleiben
- staff.seriousness wenn Patient:innen nicht ernst genommen, abgewertet oder bagatellisiert werden
- care.competence bei wahrgenommener fachlicher Kompetenz oder mangelnder Kompetenz
- coordination.discharge bei Entlassung, Entlassungsorganisation oder fehlenden Entlassungsinformationen

Vermeide Übererkennung:
- access.navigation nur bei tatsächlicher Orientierung oder Wegfindung, nicht allgemein bei Zugangsproblemen
- care.safety nur bei klarer Gefährdung, Fehler, Risiko oder Schaden
- staff.empathy als Strength nur bei explizit positivem Signal
- staff.friendliness als Strength nur bei explizit positivem Signal
""".strip()
)

SYSTEM_PROMPT_V1_4 = SYSTEM_PROMPT_V1


def build_prompt_v1_4(review_text: str, meta_json: str) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies die Review und die Metadaten unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES_V1_4}

Metadata:
{meta_json}

Review:
{review_text}
""".strip()
