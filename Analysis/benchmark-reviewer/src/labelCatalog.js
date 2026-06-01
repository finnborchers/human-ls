export const LABEL_GROUPS = [
  {
    key: "access",
    title: "Access",
    labels: [
      ["access.appointments", "Terminvergabe, Terminorganisation, Schwierigkeit einen Termin zu bekommen"],
      ["access.waiting", "Wartezeiten vor Behandlung, Untersuchung, Aufnahme oder Entlassung"],
      ["access.reachability", "Telefonische oder digitale Erreichbarkeit, Rückrufe, Kontaktaufnahme"],
      ["access.navigation", "Orientierung im Haus, Wegfindung, Auffindbarkeit von Bereichen"],
    ],
  },
  {
    key: "admin",
    title: "Admin",
    labels: [
      ["admin.registration", "Anmeldung, Aufnahme, Entlassungsformalitäten, administrative Abwicklung"],
      ["admin.paperwork", "Formulare, Dokumente, Bescheinigungen, bürokratische Unterlagen"],
      ["admin.costs", "Kosten, Abrechnung, finanzielle Belastung, unklare Gebühren"],
      ["admin.privacy", "Datenschutz, Vertraulichkeit, Preisgabe persönlicher Informationen"],
    ],
  },
  {
    key: "communication",
    title: "Communication",
    labels: [
      ["communication.communication", "Allgemeiner Kommunikationsstil, Rückmeldungen, Gesprächsbereitschaft"],
      ["communication.explanation", "Medizinische Erklärungen, Aufklärung, verständliche Erläuterung"],
      ["communication.information", "Organisatorische Informationen zu Ablauf, Zuständigkeiten und nächsten Schritten"],
      ["communication.decisions", "Einbezug in Entscheidungen, Mitsprache, Zustimmung"],
    ],
  },
  {
    key: "staff",
    title: "Staff",
    labels: [
      ["staff.friendliness", "Freundlichkeit, Höflichkeit, netter Umgang"],
      ["staff.empathy", "Mitgefühl, menschliche Zuwendung, Verständnis"],
      ["staff.respect", "Respektvoller oder abwertender Umgang, Würde, Tonfall"],
      ["staff.seriousness", "Ob Beschwerden, Schmerzen oder Sorgen ernst genommen wurden"],
    ],
  },
  {
    key: "care",
    title: "Care",
    labels: [
      ["care.diagnosis", "Richtige, falsche oder verspätete Diagnose, Nichterkennen von Ursachen"],
      ["care.treatment", "Qualität oder Angemessenheit von Behandlung, Therapie oder Versorgung"],
      ["care.medication", "Medikation, Dosierung, Gabe, Nebenwirkungen von Medikamenten"],
      ["care.symptoms", "Umgang mit konkreten Symptomen, Schmerzen oder Beschwerden"],
      ["care.safety", "Fehler, riskante Situationen, Schaden, direkte Behandlungsgefährdung"],
      ["care.competence", "Fachliche Kompetenz, Professionalität, Vertrauenswürdigkeit der Versorgung"],
    ],
  },
  {
    key: "coordination",
    title: "Coordination",
    labels: [
      ["coordination.coordination", "Abstimmung zwischen Stationen, Teams, Fachbereichen, Übergaben"],
      ["coordination.discharge", "Entlassung, Entlassungsorganisation, Vorbereitung der Entlassung"],
      ["coordination.followup", "Nachsorge, Anschlussversorgung, weitere Schritte nach der Behandlung"],
    ],
  },
  {
    key: "environment",
    title: "Environment",
    labels: [
      ["environment.cleanliness", "Sauberkeit, Hygienezustand von Zimmer, Bad, Bett oder Station"],
      ["environment.facilities", "Ausstattung, Zimmer, Gebäudezustand, Lärm, Komfort"],
      ["environment.food", "Essen, Getränke, Verpflegung"],
      ["environment.support", "Praktische Unterstützung, Hilfe im Alltag, Grundpflege"],
    ],
  },
  {
    key: "inclusion",
    title: "Inclusion",
    labels: [
      ["inclusion.language", "Sprachbarrieren zwischen Personal und Patient:innen oder Angehörigen"],
      ["inclusion.interpreting", "Dolmetschen, Übersetzungshilfe, Sprachmittlung"],
      ["inclusion.equality", "Diskriminierung, ungleiche Behandlung, rassistische Abwertung"],
      ["inclusion.culture", "Kulturelle Sensibilität, Umgang mit kulturellen oder religiösen Bedürfnissen"],
      ["inclusion.asylum", "Bezug zu Flucht, Asyl, Aufenthaltsstatus oder daraus resultierender Behandlung"],
    ],
  },
];

export const LABEL_DESCRIPTIONS = Object.fromEntries(
  LABEL_GROUPS.flatMap((group) => group.labels),
);
