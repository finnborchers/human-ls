from prompt_flat_v1 import LABEL_GUIDELINES_V1, SYSTEM_PROMPT_V1


LABEL_GUIDELINES_V1_3 = LABEL_GUIDELINES_V1
SYSTEM_PROMPT_V1_3 = SYSTEM_PROMPT_V1


def build_prompt_v1_3(review_text: str, meta_json: str) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies die Review und die ausgewählten Metadaten unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES_V1_3}

Metadata:
{meta_json}

Review:
{review_text}
""".strip()
