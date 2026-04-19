import { METRICS, formatMetricValue, formatPercent, formatReviewShare } from "../lib/metrics.js";

function MetricCell({ label, value, accent }) {
  return (
    <div className="metric-cell">
      <span className="metric-cell__label">{label}</span>
      <span className="metric-cell__value" style={{ color: accent }}>
        {value}
      </span>
    </div>
  );
}

export default function ClinicPanel({ clinic, metricKey, baseline, accentColor }) {
  if (!clinic) {
    return (
      <aside className="clinic-panel clinic-panel--empty">
        <p className="eyebrow">Klinikdetail</p>
        <h2>Keine Klinik ausgewaehlt</h2>
        <p>
          Fahre ueber einen Punkt auf der Karte, um erste Details zu sehen. Mit einem Klick
          oeffnest du die Klinik dauerhaft im Panel und kannst sie mit dem Durchschnitt in
          Niedersachsen vergleichen.
        </p>
      </aside>
    );
  }

  const activeMetric = METRICS[metricKey];
  const snippets = clinic.snippets?.[metricKey] ?? [];

  return (
    <aside className="clinic-panel">
      <p className="eyebrow">Klinikdetail</p>
      <h2>{clinic.clinic_name}</h2>
      <p className="clinic-panel__location">{clinic.review_count} ausgewertete Rezensionen</p>

      <section className="clinic-panel__lead">
        <div>
          <p className="clinic-panel__kicker">{activeMetric.label}</p>
          <p className="clinic-panel__hero" style={{ color: accentColor }}>
            {formatMetricValue(clinic, metricKey)}
          </p>
        </div>
        <div className="clinic-panel__compare">
          <span>Durchschnitt in Niedersachsen</span>
          <strong>{formatPercent(baseline)}</strong>
        </div>
      </section>

      <section className="clinic-panel__explanation">
        <p className="clinic-panel__meaning">{activeMetric.meaning}</p>
        <p className="clinic-panel__meaning-strong">{formatReviewShare(clinic.metrics?.[metricKey])}</p>
      </section>

      <section className="clinic-panel__grid">
        <MetricCell label="Wartezeit" value={formatMetricValue(clinic, "waiting")} accent={accentColor} />
        <MetricCell
          label="Kommunikation"
          value={formatMetricValue(clinic, "communication")}
          accent={accentColor}
        />
        <MetricCell label="Prozesse" value={formatMetricValue(clinic, "process")} accent={accentColor} />
        <MetricCell
          label="Sprache + Diskr."
          value={formatMetricValue(clinic, "languageDiscrimination")}
          accent={accentColor}
        />
        <MetricCell
          label="Anteil 1-2 Sterne"
          value={formatPercent(clinic.low_star_share)}
          accent={accentColor}
        />
        <MetricCell
          label="Durchschnitt Sterne"
          value={clinic.avg_star?.toFixed(2) ?? "k. A."}
          accent={accentColor}
        />
      </section>

      <section className="clinic-panel__themes">
        <p className="eyebrow">Auffaellige Themen</p>
        <div className="clinic-panel__chips">
          {(clinic.top_themes || []).map((theme) => (
            <span className="theme-chip" key={theme.key}>
              {theme.label} {formatPercent(theme.value)}
            </span>
          ))}
        </div>
      </section>

      <section className="clinic-panel__quotes">
        <p className="eyebrow">Beispielhafte Signale</p>
        {snippets.length === 0 ? (
          <p className="clinic-panel__muted">
            Fuer diese Themenebene wurde kein kurzer Textausschnitt extrahiert. Die Klinik bleibt
            dennoch ueber ihre aggregierten Werte in der Karte sichtbar.
          </p>
        ) : (
          snippets.map((snippet, index) => (
            <blockquote className="snippet-card" key={`${clinic.place_id}-${metricKey}-${index}`}>
              <p>{snippet.text}</p>
              <footer>{snippet.star_rating}-Sterne-Rezension</footer>
            </blockquote>
          ))
        )}
      </section>

      <section className="clinic-panel__quality">
        <p className="eyebrow">Datennotizen</p>
        <div className="clinic-panel__chips">
          {(clinic.quality_flags || []).map((flag) => (
            <span className="quality-chip" key={flag}>
              {flag.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      </section>
    </aside>
  );
}
