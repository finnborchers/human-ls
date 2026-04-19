import { Suspense, lazy, startTransition, useCallback, useEffect, useMemo, useState } from "react";
import ClinicPanel from "./components/ClinicPanel.jsx";
import MetricToggle from "./components/MetricToggle.jsx";
import {
  METRICS,
  formatPercent,
  getMetricColor,
  getMetricValue,
  rgbaString,
} from "./lib/metrics.js";

const MapScene = lazy(() => import("./components/MapScene.jsx"));

function meanMetric(clinics, metricKey) {
  if (clinics.length === 0) {
    return 0;
  }

  const total = clinics.reduce((sum, clinic) => sum + getMetricValue(clinic, metricKey), 0);
  return total / clinics.length;
}

export default function App() {
  const [payload, setPayload] = useState(null);
  const [boundary, setBoundary] = useState(null);
  const [selectedMetric, setSelectedMetric] = useState("waiting");
  const [selectedPlaceId, setSelectedPlaceId] = useState(null);
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetch("/data/clinics.json").then((response) => {
        if (!response.ok) {
          throw new Error("Could not load clinic dataset.");
        }
        return response.json();
      }),
      fetch("/data/lower-saxony.geojson").then((response) => {
        if (!response.ok) {
          throw new Error("Could not load Lower Saxony boundary.");
        }
        return response.json();
      }),
    ])
      .then(([dataset, boundaryFeatureCollection]) => {
        if (cancelled) {
          return;
        }

        setPayload(dataset);
        setBoundary(boundaryFeatureCollection);
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(caughtError.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const clinics = payload?.clinics ?? [];
  const visibleClinics = useMemo(
    () => clinics.filter((clinic) => !(clinic.quality_flags || []).includes("outside_lower_saxony")),
    [clinics],
  );

  useEffect(() => {
    if (selectedPlaceId || visibleClinics.length === 0) {
      return;
    }

    const strongest = [...visibleClinics].sort(
      (left, right) => getMetricValue(right, selectedMetric) - getMetricValue(left, selectedMetric),
    )[0];

    if (strongest) {
      setSelectedPlaceId(strongest.place_id);
    }
  }, [selectedMetric, selectedPlaceId, visibleClinics]);

  const selectedClinic = useMemo(
    () => visibleClinics.find((clinic) => clinic.place_id === selectedPlaceId) ?? visibleClinics[0],
    [selectedPlaceId, visibleClinics],
  );

  const statewideMean = useMemo(() => meanMetric(visibleClinics, selectedMetric), [selectedMetric, visibleClinics]);

  const hotspots = useMemo(
    () =>
      [...visibleClinics]
        .sort((left, right) => getMetricValue(right, selectedMetric) - getMetricValue(left, selectedMetric))
        .slice(0, 5),
    [selectedMetric, visibleClinics],
  );

  const accentColor = rgbaString(getMetricColor(getMetricValue(selectedClinic, selectedMetric)));
  const handleMapSelect = useCallback((placeId) => {
    startTransition(() => {
      setSelectedPlaceId(placeId);
    });
  }, []);

  if (error) {
    return (
      <main className="app-shell">
        <section className="error-state">
          <p className="eyebrow">Fehler beim Start</p>
          <h1>{error}</h1>
          <p>
            Der Datensatz oder die Grenzgeometrie fehlt. Fuehre <code>npm run build:data</code>
            im Ordner <code>website/</code> aus und lade die Seite danach neu.
          </p>
        </section>
      </main>
    );
  }

  if (!payload || !boundary) {
    return (
      <main className="app-shell">
        <section className="loading-state">
          <p className="eyebrow">Niedersachsen</p>
          <h1>Atlas wird vorbereitet</h1>
          <p>Grenzen, Klinikdaten und interaktive Ebenen werden geladen.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <MetricToggle
        activeMetric={selectedMetric}
        visibleClinicCount={visibleClinics.length}
        totalReviews={payload.sourceSummary.totalReviews.toLocaleString("de-DE")}
        onChange={(metricKey) => {
          startTransition(() => {
            setSelectedMetric(metricKey);
          });
        }}
      />

      <section className="atlas-layout">
        <div className="atlas-layout__map">
          <div className="map-frame">
            <Suspense
              fallback={
                <div className="map-loading">
                  <p className="eyebrow">Karte wird geladen</p>
                  <p>Interaktive Ebenen und Klinikpunkte werden initialisiert.</p>
                </div>
              }
            >
              <MapScene
                clinics={visibleClinics}
                boundary={boundary}
                metricKey={selectedMetric}
                selectedPlaceId={selectedClinic?.place_id}
                onHover={setHoveredPoint}
                onSelect={handleMapSelect}
              />
            </Suspense>

            <aside className="map-overlay map-overlay--left">
              <p className="eyebrow">Auffaellige Kliniken</p>
              <p className="map-overlay__text">
                Die Liste zeigt die Kliniken mit den hoechsten Werten in der aktuell gewaehlten
                Themenebene.
              </p>
              <div className="hotspot-list">
                {hotspots.map((clinic) => (
                  <button
                    key={clinic.place_id}
                    type="button"
                    className={`hotspot-item${
                      clinic.place_id === selectedClinic?.place_id ? " is-active" : ""
                    }`}
                    onClick={() => setSelectedPlaceId(clinic.place_id)}
                  >
                    <span className="hotspot-item__title">{clinic.clinic_name}</span>
                    <span className="hotspot-item__meta">
                      {formatPercent(getMetricValue(clinic, selectedMetric))} der Rezensionen ·{" "}
                      {clinic.review_count} insgesamt
                    </span>
                  </button>
                ))}
              </div>
            </aside>

            {isInfoOpen ? (
              <aside className="map-overlay map-overlay--right map-overlay--info">
                <div className="map-overlay__header">
                  <p className="eyebrow">So liest du die Karte</p>
                  <button
                    type="button"
                    className="map-info-close"
                    onClick={() => setIsInfoOpen(false)}
                    aria-label="Hinweis schliessen"
                  >
                    x
                  </button>
                </div>
                <p className="map-overlay__text">
                  Jeder Punkt steht fuer eine Klinik. Je kraeftiger die Farbe, desto haeufiger
                  kommt das gewaehlte Thema in den ausgewerteten Rezensionen vor.
                </p>
                <p className="map-overlay__text">
                  Beispiel: 52% bedeutet, dass in etwa 52 von 100 ausgewerteten Rezensionen dieser
                  Klinik Hinweise auf das ausgewaehlte Thema gefunden wurden.
                </p>
              </aside>
            ) : (
              <button
                type="button"
                className="map-info-toggle"
                onClick={() => setIsInfoOpen(true)}
              >
                Info
              </button>
            )}

            {hoveredPoint?.clinic ? (
              <div
                className="map-tooltip"
                style={{
                  left: `${hoveredPoint.x}px`,
                  top: `${hoveredPoint.y}px`,
                  borderColor: accentColor,
                }}
              >
                <strong>{hoveredPoint.clinic.clinic_name}</strong>
                <span>{formatPercent(getMetricValue(hoveredPoint.clinic, selectedMetric))}</span>
                <small>
                  {hoveredPoint.clinic.review_count} Rezensionen · {METRICS[selectedMetric].shortLabel}
                </small>
              </div>
            ) : null}
          </div>
        </div>

        <ClinicPanel
          clinic={selectedClinic}
          metricKey={selectedMetric}
          baseline={statewideMean}
          accentColor={accentColor}
        />
      </section>

      <section className="footer-strip">
        <p>
          Datengrundlage: <code>configs/place_urls.json</code>,{" "}
          <code>artifacts/capture_reviews_run_summary.json</code> und die jeweiligen{" "}
          <code>reviews.json</code>-Dateien pro Klinik. Die Darstellung ist ein analytischer
          Prototyp und keine medizinische oder qualitative Gesamtbewertung einer Klinik.
        </p>
      </section>
    </main>
  );
}
