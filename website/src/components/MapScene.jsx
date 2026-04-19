import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import { getMetricColor, getMetricValue, rgbaString } from "../lib/metrics.js";
import "maplibre-gl/dist/maplibre-gl.css";

const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const DEFAULT_BOUNDS = [
  [6.45, 51.18],
  [11.92, 54.08],
];

function getFeatureBounds(featureCollection) {
  const bounds = new maplibregl.LngLatBounds();

  featureCollection.features.forEach((feature) => {
    const geometry = feature.geometry;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;

    polygons.forEach((polygon) => {
      polygon.forEach((ring) => {
        ring.forEach(([lng, lat]) => bounds.extend([lng, lat]));
      });
    });
  });

  return bounds;
}

function clinicsToFeatureCollection(clinics, metricKey, selectedPlaceId) {
  return {
    type: "FeatureCollection",
    features: clinics.map((clinic) => {
      const metricValue = getMetricValue(clinic, metricKey);

      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [clinic.lon, clinic.lat],
        },
        properties: {
          place_id: clinic.place_id,
          clinic_name: clinic.clinic_name,
          review_count: clinic.review_count,
          metric_value: metricValue,
          is_selected: clinic.place_id === selectedPlaceId ? 1 : 0,
        },
      };
    }),
  };
}

function syncBoundary(map, boundary) {
  if (!boundary || !map.isStyleLoaded()) {
    return;
  }

  const source = map.getSource("lower-saxony-outline");
  if (source) {
    source.setData(boundary);
    return;
  }

  map.addSource("lower-saxony-outline", {
    type: "geojson",
    data: boundary,
  });

  map.addLayer({
    id: "lower-saxony-fill",
    type: "fill",
    source: "lower-saxony-outline",
    paint: {
      "fill-color": "#d9ecea",
      "fill-opacity": 0.1,
    },
  });

  map.addLayer({
    id: "lower-saxony-line",
    type: "line",
    source: "lower-saxony-outline",
    paint: {
      "line-color": "#1c7881",
      "line-width": 1.8,
      "line-opacity": 0.9,
    },
  });
}

function syncClinics(map, data) {
  if (!map.isStyleLoaded()) {
    return;
  }

  const source = map.getSource("clinics");
  if (source) {
    source.setData(data);
    return;
  }

  map.addSource("clinics", {
    type: "geojson",
    data,
  });

  map.addLayer({
    id: "clinic-heat",
    type: "heatmap",
    source: "clinics",
    maxzoom: 11,
    paint: {
      "heatmap-weight": [
        "interpolate",
        ["linear"],
        ["get", "metric_value"],
        0,
        0,
        1,
        1,
      ],
      "heatmap-intensity": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        0.55,
        8,
        1.1,
      ],
      "heatmap-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        18,
        8,
        34,
        11,
        48,
      ],
      "heatmap-opacity": 0.5,
      "heatmap-color": [
        "interpolate",
        ["linear"],
        ["heatmap-density"],
        0,
        "rgba(255,255,255,0)",
        0.2,
        "rgba(112,188,197,0.25)",
        0.4,
        "rgba(82,182,191,0.35)",
        0.6,
        "rgba(242,201,106,0.45)",
        0.8,
        "rgba(245,139,76,0.65)",
        1,
        "rgba(218,76,76,0.82)",
      ],
    },
  });

  map.addLayer({
    id: "clinic-halo",
    type: "circle",
    source: "clinics",
    minzoom: 4,
    paint: {
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["sqrt", ["max", ["get", "review_count"], 12]],
        3.5,
        9,
        10,
        13,
        20,
        18,
      ],
      "circle-color": "rgba(255,255,255,0)",
      "circle-stroke-width": [
        "case",
        ["==", ["get", "is_selected"], 1],
        5,
        2.5,
      ],
      "circle-stroke-color": [
        "case",
        ["==", ["get", "is_selected"], 1],
        "rgba(14,87,95,0.42)",
        "rgba(255,255,255,0.88)",
      ],
      "circle-opacity": 1,
    },
  });

  map.addLayer({
    id: "clinic-points",
    type: "circle",
    source: "clinics",
    minzoom: 4,
    paint: {
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["sqrt", ["max", ["get", "review_count"], 12]],
        3.5,
        7,
        10,
        11.5,
        20,
        15,
      ],
      "circle-color": [
        "interpolate",
        ["linear"],
        ["get", "metric_value"],
        0,
        "rgb(86,190,197)",
        0.25,
        "rgb(64,208,175)",
        0.5,
        "rgb(244,200,96)",
        0.75,
        "rgb(247,137,72)",
        1,
        "rgb(244,88,88)",
      ],
      "circle-stroke-width": [
        "case",
        ["==", ["get", "is_selected"], 1],
        3,
        1.5,
      ],
      "circle-stroke-color": [
        "case",
        ["==", ["get", "is_selected"], 1],
        "rgba(255,255,255,1)",
        "rgba(14,87,95,0.85)",
      ],
      "circle-opacity": 0.94,
    },
  });
}

export default function MapScene({
  clinics,
  boundary,
  metricKey,
  selectedPlaceId,
  onSelect,
  onHover,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const onHoverRef = useRef(onHover);
  const onSelectRef = useRef(onSelect);
  const boundaryRef = useRef(boundary);
  const clinicsById = useMemo(
    () => new Map(clinics.map((clinic) => [clinic.place_id, clinic])),
    [clinics],
  );
  const clinicsGeoJson = useMemo(
    () => clinicsToFeatureCollection(clinics, metricKey, selectedPlaceId),
    [clinics, metricKey, selectedPlaceId],
  );
  const clinicsGeoJsonRef = useRef(clinicsGeoJson);

  useEffect(() => {
    onHoverRef.current = onHover;
  }, [onHover]);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    boundaryRef.current = boundary;
  }, [boundary]);

  useEffect(() => {
    clinicsGeoJsonRef.current = clinicsGeoJson;
  }, [clinicsGeoJson]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return undefined;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: [9.42, 52.74],
      zoom: 6.4,
      pitch: 44,
      bearing: -11,
      antialias: true,
    });

    mapRef.current = map;

    map.addControl(
      new maplibregl.NavigationControl({
        showCompass: false,
      }),
      "top-right",
    );

    map.on("load", () => {
      syncBoundary(map, boundaryRef.current);
      syncClinics(map, clinicsGeoJsonRef.current);

      const bounds = boundaryRef.current ? getFeatureBounds(boundaryRef.current) : DEFAULT_BOUNDS;
      map.fitBounds(bounds, {
        padding: 72,
        duration: 0,
      });

      map.easeTo({
        pitch: 54,
        bearing: -14,
        duration: 2400,
      });
    });

    map.on("styledata", () => {
      syncBoundary(map, boundaryRef.current);
      syncClinics(map, clinicsGeoJsonRef.current);
    });

    return () => {
      markersRef.current.forEach((entry) => entry.marker.remove());
      markersRef.current = [];
      mapRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    syncBoundary(map, boundary);
    syncClinics(map, clinicsGeoJson);
  }, [boundary, clinicsGeoJson]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    markersRef.current.forEach((entry) => {
      entry.element.removeEventListener("mouseenter", entry.handleMouseEnter);
      entry.element.removeEventListener("mouseleave", entry.handleMouseLeave);
      entry.element.removeEventListener("click", entry.handleClick);
      entry.marker.remove();
    });

    markersRef.current = clinics.map((clinic) => {
      const metricValue = getMetricValue(clinic, metricKey);
      const markerColor = rgbaString(getMetricColor(metricValue));
      const markerSize =
        clinic.place_id === selectedPlaceId
          ? 28
          : Math.max(16, Math.min(22, 10 + Math.sqrt(clinic.review_count || 0) / 2));

      const element = document.createElement("button");
      element.type = "button";
      element.className = `clinic-pin${clinic.place_id === selectedPlaceId ? " is-selected" : ""}`;
      element.style.setProperty("--pin-color", markerColor);
      element.style.setProperty("--pin-size", `${markerSize}px`);
      element.setAttribute("aria-label", clinic.clinic_name);

      const marker = new maplibregl.Marker({
        element,
        anchor: "center",
      })
        .setLngLat([clinic.lon, clinic.lat])
        .addTo(map);

      const handleMouseEnter = () => {
        const point = map.project([clinic.lon, clinic.lat]);
        onHoverRef.current({
          clinic,
          x: point.x,
          y: point.y,
        });
      };

      const handleMouseLeave = () => {
        onHoverRef.current(null);
      };

      const handleClick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        onSelectRef.current(clinic.place_id);
      };

      element.addEventListener("mouseenter", handleMouseEnter);
      element.addEventListener("mouseleave", handleMouseLeave);
      element.addEventListener("click", handleClick);

      return {
        marker,
        element,
        handleMouseEnter,
        handleMouseLeave,
        handleClick,
      };
    });

    return () => {
      markersRef.current.forEach((entry) => {
        entry.element.removeEventListener("mouseenter", entry.handleMouseEnter);
        entry.element.removeEventListener("mouseleave", entry.handleMouseLeave);
        entry.element.removeEventListener("click", entry.handleClick);
        entry.marker.remove();
      });
      markersRef.current = [];
    };
  }, [clinics, metricKey, selectedPlaceId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedPlaceId) {
      return;
    }

    const clinic = clinicsById.get(selectedPlaceId);
    if (!clinic) {
      return;
    }

    map.easeTo({
      center: [clinic.lon, clinic.lat],
      zoom: 8.3,
      pitch: 58,
      bearing: -18,
      duration: 1100,
    });
  }, [clinicsById, selectedPlaceId]);

  return <div className="map-scene" ref={containerRef} />;
}
