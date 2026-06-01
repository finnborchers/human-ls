LABEL_GUIDE_V2 = """
Extrahiere aus jeder Krankenhausbewertung nur zwei Listen:
- problem_labels
- strength_labels

Nutze ausschließlich die folgenden Labels. Die Schlüssel bleiben englisch, die Bedeutung ist hier auf Deutsch erklärt:

access.appointments: Terminvergabe, Terminorganisation, Schwierigkeit einen Termin zu bekommen oder zu verschieben
access.waiting: Wartezeiten vor Behandlung, Untersuchung, Aufnahme, Entlassung oder Rückmeldung vor Ort
access.reachability: telefonische oder digitale Erreichbarkeit, Rückrufe, Kontaktaufnahme
access.navigation: Orientierung im Haus, Wegfindung, Auffindbarkeit von Bereichen oder Ansprechpersonen

admin.registration: Anmeldung, Aufnahme, Entlassungsformalitäten, administrative Abwicklung am Schalter
admin.paperwork: Formulare, Bescheinigungen, Dokumente, bürokratische Unterlagen
admin.costs: Kosten, Abrechnung, finanzielle Belastung, unklare Gebühren
admin.privacy: Datenschutz, Vertraulichkeit, Preisgabe persönlicher oder medizinischer Informationen

communication.communication: allgemeiner Umgang in der Kommunikation, Gesprächsbereitschaft, Rückmeldungen, Tonfall ohne Fokus auf Detailkategorie
communication.explanation: medizinische Erklärungen, Aufklärung, verständliche Erläuterung von Diagnose, Behandlung oder Risiken
communication.information: organisatorische Informationen zum Ablauf, Termine, Zuständigkeiten, Warteprozess, Station oder nächste Schritte
communication.decisions: Einbezug in Entscheidungen, Mitsprache, Zustimmung, über den Kopf hinweg getroffene Entscheidungen

staff.friendliness: Freundlichkeit, Höflichkeit, netter Umgang
staff.empathy: Mitgefühl, menschliche Zuwendung, Verständnis für Ängste oder Belastung
staff.respect: respektvoller oder abwertender Umgang, Würde, Ton gegenüber Patient:innen oder Angehörigen
staff.seriousness: ob Beschwerden, Schmerzen oder Sorgen ernst genommen oder bagatellisiert wurden

care.diagnosis: richtige, falsche oder verspätete Diagnose, Nichterkennen von Ursachen oder Beschwerden
care.treatment: Qualität, Angemessenheit oder Erfolg der Behandlung, Therapie, Versorgung oder des Eingriffs
care.medication: Medikation, Schmerzmittel, Dosierung, Gabe, Auslassen oder Nebenwirkungen von Medikamenten
care.symptoms: Umgang mit konkreten Symptomen, Schmerzen, Beschwerden oder deren Linderung
care.safety: Fehler, riskante Situationen, Schaden, vermeidbare Gefährdung, Hygiene- oder Sicherheitsprobleme mit direktem Behandlungsbezug
care.competence: fachliche Kompetenz, Professionalität, Können, Vertrauenswürdigkeit der medizinischen Versorgung

coordination.coordination: Abstimmung zwischen Stationen, Teams, Fachbereichen, Übergaben, interne Zusammenarbeit
coordination.discharge: Entlassung, Entlassungsorganisation, Vorbereitung der Entlassung
coordination.followup: Nachsorge, weitere Schritte nach dem Aufenthalt, Anschlussversorgung, Rückfragen nach der Behandlung

environment.cleanliness: Sauberkeit, Hygienezustand von Zimmern, Bad, Bett, Station oder Umgebung ohne direkten medizinischen Fehlerbezug
environment.facilities: Ausstattung, Zimmer, Gebäudezustand, Lärm, Komfort, technische oder räumliche Bedingungen
environment.food: Essen, Getränke, Verpflegung
environment.support: praktische Unterstützung im Alltag, Hilfe auf Station, Grundpflege, Unterstützung bei Wegen oder Bedürfnissen

inclusion.language: Sprachbarrieren zwischen Personal und Patient:innen oder Angehörigen
inclusion.interpreting: Dolmetschen, Übersetzungshilfe, Bereitstellung oder Fehlen von Sprachmittlung
inclusion.equality: Diskriminierung, ungleiche Behandlung, rassistische oder andere abwertende Ungleichbehandlung
inclusion.culture: kulturelle Sensibilität, Umgang mit kulturellen oder religiösen Bedürfnissen
inclusion.asylum: Bezug zu Flucht, Asyl, Aufenthaltsstatus oder daraus resultierender besonderer Behandlung

Wichtige Abgrenzungen:
- access.appointments betrifft das Bekommen oder Organisieren eines Termins; access.waiting betrifft die Dauer des Wartens vor Ort oder bis zur Leistung.
- communication.explanation betrifft medizinische Erklärungen; communication.information betrifft organisatorische Auskünfte und Ablaufinfos.
- care.diagnosis betrifft das Erkennen und Benennen des Problems; care.treatment betrifft das anschließende therapeutische Handeln.
- staff.respect betrifft respektvollen oder abwertenden Umgang; staff.seriousness betrifft, ob Beschwerden ernst genommen werden.
- environment.cleanliness betrifft Sauberkeit der Umgebung; care.safety betrifft Gefährdung, Fehler oder Schaden mit Behandlungsbezug.
- coordination.discharge betrifft die Entlassung selbst; coordination.followup betrifft Nachsorge oder weitere Schritte nach der Entlassung.

Globale Regeln:
- Verwende nur Informationen aus dem Reviewtext.
- Verwende keine Metadaten, keine Sternbewertung und keine vermutete Gesamtstimmung.
- Setze nur Labels, die explizit oder klar textnah belegt sind.
- Erfinde keine Labels und verwende keine freien Formulierungen.
- Wenn kein passendes Label vorhanden ist, lasse die Liste leer.
- Wenn derselbe Aspekt sowohl positiv als auch negativ beschrieben ist, darf derselbe Labelpfad in beiden Listen vorkommen.
- Lieber leer lassen als raten.
""".strip()


SYSTEM_PROMPT_V2 = "You extract structured information from German hospital reviews and respond only with valid JSON."


def build_prompt_v2(review_text: str) -> str:
    return f"""
Du extrahierst strukturierte Informationen aus einer deutschen Krankenhausbewertung.
Gib nur die JSON-Struktur des Schemas zurück.

{LABEL_GUIDE_V2}

Review:
{review_text}
""".strip()
