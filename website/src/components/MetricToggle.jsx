import { METRICS, METRIC_ORDER } from "../lib/metrics.js";

export default function MetricToggle({
  activeMetric,
  visibleClinicCount,
  totalReviews,
  onChange,
}) {
  return (
    <section className="metric-toggle">
      <div className="metric-toggle__top">
        <div className="metric-toggle__hero">
          <p className="eyebrow">Niedersachsen</p>
          <h1>HUMAN-LS</h1>
          <p className="metric-toggle__lede">
            Interaktive Karte zu Wartezeiten, Barrieren und Erfahrungen in Kliniken in
            Niedersachsen.
          </p>
        </div>

        <div className="metric-toggle__summary">
          <div className="summary-card">
            <span className="summary-card__label">Sichtbare Kliniken</span>
            <strong>{visibleClinicCount}</strong>
          </div>
          <div className="summary-card">
            <span className="summary-card__label">Ausgewertete Rezensionen</span>
            <strong>{totalReviews}</strong>
          </div>
          <div className="summary-card">
            <span className="summary-card__label">Aktive Themenebene</span>
            <strong>{METRICS[activeMetric].label}</strong>
          </div>
        </div>
      </div>

      <div className="metric-toggle__header">
        <p className="eyebrow">Themenebene</p>
      </div>
      <div className="metric-toggle__grid">
        {METRIC_ORDER.map((metricKey) => {
          const metric = METRICS[metricKey];
          const isActive = metricKey === activeMetric;

          return (
            <button
              key={metricKey}
              type="button"
              className={`metric-toggle__button${isActive ? " is-active" : ""}`}
              onClick={() => onChange(metricKey)}
            >
              <span className="metric-toggle__label">{metric.label}</span>
              <span className="metric-toggle__description">{metric.description}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
