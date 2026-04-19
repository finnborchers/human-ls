export const METRIC_ORDER = [
  "waiting",
  "communication",
  "process",
  "languageDiscrimination",
];

export const METRICS = {
  waiting: {
    label: "Wartezeit",
    shortLabel: "Warte- und Zugangsprobleme",
    description:
      "Zeigt Rezensionen mit Hinweisen auf lange Wartezeiten, Terminprobleme oder stockende Ablaeufe in der Aufnahme.",
    meaning:
      "Der Prozentwert zeigt, in wie vielen ausgewerteten Rezensionen Hinweise auf Warte- oder Zugangsprobleme vorkommen.",
  },
  communication: {
    label: "Kommunikation",
    shortLabel: "Umgang und Respekt",
    description:
      "Zeigt Rezensionen mit Hinweisen auf unklare Kommunikation, mangelnden Respekt oder das Gefuehl, nicht ernst genommen zu werden.",
    meaning:
      "Der Prozentwert zeigt, in wie vielen ausgewerteten Rezensionen Probleme im Umgang, in der Ansprache oder in der Kommunikation auftauchen.",
  },
  process: {
    label: "Prozesse",
    shortLabel: "Organisation und Prozesse",
    description:
      "Zeigt Rezensionen mit Hinweisen auf organisatorische Reibung, Verwaltungsprobleme oder chaotische Ablaeufe.",
    meaning:
      "Der Prozentwert zeigt, in wie vielen ausgewerteten Rezensionen organisatorische oder administrative Probleme beschrieben werden.",
  },
  languageDiscrimination: {
    label: "Sprache + Diskriminierung",
    shortLabel: "Sprache und Benachteiligung",
    description:
      "Zeigt Rezensionen mit Hinweisen auf Sprachbarrieren, fehlende Uebersetzung oder explizite Diskriminierungserfahrungen.",
    meaning:
      "Der Prozentwert zeigt, in wie vielen ausgewerteten Rezensionen Sprachbarrieren oder Hinweise auf Diskriminierung vorkommen.",
  },
};

export function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "k. A.";
  }

  return `${Math.round(value * 100)}%`;
}

export function formatReviewShare(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "Kein belastbarer Wert vorhanden.";
  }

  return `${Math.round(value * 100)} von 100 ausgewerteten Rezensionen enthalten dieses Signal.`;
}

export function formatMetricValue(clinic, metricKey) {
  return formatPercent(clinic?.metrics?.[metricKey]);
}

export function getMetricValue(clinic, metricKey) {
  return clinic?.metrics?.[metricKey] ?? 0;
}

export function getMetricColor(value) {
  const safe = Math.max(0, Math.min(1, value || 0));
  const stops = [
    { at: 0, color: [86, 190, 197] },
    { at: 0.25, color: [64, 208, 175] },
    { at: 0.5, color: [244, 200, 96] },
    { at: 0.75, color: [247, 137, 72] },
    { at: 1, color: [244, 88, 88] },
  ];

  const upperIndex = stops.findIndex((stop) => safe <= stop.at);
  const upper = stops[Math.max(upperIndex, 1)];
  const lower = stops[Math.max(upperIndex - 1, 0)];
  const span = upper.at - lower.at || 1;
  const mix = (safe - lower.at) / span;

  return lower.color.map((channel, index) =>
    Math.round(channel + (upper.color[index] - channel) * mix),
  );
}

export function rgbaString(rgb, alpha = 1) {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}
