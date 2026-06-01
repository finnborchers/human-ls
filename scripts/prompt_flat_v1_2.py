from prompt_flat_v1 import LABEL_GUIDELINES_V1, SYSTEM_PROMPT_V1


LABEL_GUIDELINES_V1_2 = LABEL_GUIDELINES_V1
SYSTEM_PROMPT_V1_2 = SYSTEM_PROMPT_V1


def build_prompt_v1_2(review_text: str) -> str:
    return f"""
Du bist ein Modell für strukturierte Informationsextraktion aus Krankenhausbewertungen.
Lies nur die Review unten.
Fülle die Felder des Pydantic-Modells exakt so aus, wie sie definiert sind.

Labels:
{LABEL_GUIDELINES_V1_2}

Review:
{review_text}
""".strip()
