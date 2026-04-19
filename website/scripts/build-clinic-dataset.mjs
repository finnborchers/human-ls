import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..", "..");
const websiteDir = path.resolve(__dirname, "..");

const captureSummaryPath = path.join(rootDir, "artifacts", "capture_reviews_run_summary.json");
const placeUrlsPath = path.join(rootDir, "configs", "place_urls.json");
const outPath = path.join(websiteDir, "public", "data", "clinics.json");

const LOWER_SAXONY_BOUNDS = {
  minLat: 51.18,
  maxLat: 54.12,
  minLon: 6.4,
  maxLon: 11.95,
};

const THEME_CONFIG = {
  waiting: {
    label: "Wartezeit",
    keywords: [
      "wartezeit",
      "gewartet",
      "stunden",
      "stunde",
      "warten",
      "termin",
      "notaufnahme",
      "aufnahme",
      "schlange",
    ],
  },
  communication: {
    label: "Kommunikation",
    keywords: [
      "unfreund",
      "respekt",
      "arrog",
      "beleidig",
      "ignor",
      "nicht ernst",
      "empath",
      "frech",
      "unhoeflich",
      "unhöflich",
      "kommun",
    ],
  },
  process: {
    label: "Prozesse",
    keywords: [
      "organisation",
      "organis",
      "chaos",
      "ablauf",
      "anmeldung",
      "verwaltung",
      "abrechnung",
      "plan",
      "entlass",
      "buerokr",
      "bürokr",
      "prozess",
    ],
  },
  languageDiscrimination: {
    label: "Sprache + Diskriminierung",
    keywords: [
      "sprach",
      "deutsch",
      "englisch",
      "dolmetsch",
      "uebersetz",
      "übersetz",
      "rass",
      "diskrimin",
      "auslaender",
      "ausländer",
      "migrant",
      "herkunft",
    ],
  },
};

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .replace(/\s+/g, " ")
    .trim();
}

function sanitizeSnippet(value) {
  return String(value || "")
    .replace(/\bdr\.?\s+[A-ZÄÖÜ][a-zäöüß-]+/g, "Dr. [redacted]")
    .replace(/\b(herr|frau)\s+[A-ZÄÖÜ][a-zäöüß-]+/gi, "$1 [redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

function parseCoordinates(url) {
  if (!url) {
    return null;
  }

  const pinMatch = url.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
  const cameraMatch = url.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);

  if (!pinMatch && !cameraMatch) {
    return null;
  }

  const pin = pinMatch
    ? {
        lat: Number.parseFloat(pinMatch[1]),
        lon: Number.parseFloat(pinMatch[2]),
      }
    : null;
  const camera = cameraMatch
    ? {
        lat: Number.parseFloat(cameraMatch[1]),
        lon: Number.parseFloat(cameraMatch[2]),
      }
    : null;

  const chosen = pin || camera;
  let coordMismatch = false;

  if (pin && camera) {
    const distance = Math.hypot(pin.lat - camera.lat, pin.lon - camera.lon);
    coordMismatch = distance > 0.15;
  }

  return {
    lat: chosen.lat,
    lon: chosen.lon,
    coordMismatch,
  };
}

function isInsideLowerSaxony(lat, lon) {
  return (
    lat >= LOWER_SAXONY_BOUNDS.minLat &&
    lat <= LOWER_SAXONY_BOUNDS.maxLat &&
    lon >= LOWER_SAXONY_BOUNDS.minLon &&
    lon <= LOWER_SAXONY_BOUNDS.maxLon
  );
}

function classifyReview(reviewText) {
  const normalized = normalizeText(reviewText);
  const hits = {};

  for (const [key, config] of Object.entries(THEME_CONFIG)) {
    hits[key] = config.keywords.some((keyword) => normalized.includes(keyword));
  }

  return hits;
}

function extractCity(placeName) {
  const fragments = String(placeName || "").split(/\s+/);
  return fragments.slice(-1)[0] || "";
}

function getTopThemes(metrics) {
  return Object.entries(metrics)
    .map(([key, value]) => ({
      key,
      label: THEME_CONFIG[key].label,
      value,
    }))
    .sort((left, right) => right.value - left.value)
    .slice(0, 3);
}

const captureSummary = JSON.parse(await readFile(captureSummaryPath, "utf8"));
const placeUrls = JSON.parse(await readFile(placeUrlsPath, "utf8"));

const clinics = [];
let totalReviews = 0;

for (const place of captureSummary.places) {
  if (!place.reviews_path) {
    continue;
  }

  const placeConfig = placeUrls[place.place_id];
  const coords = parseCoordinates(placeConfig?.resolved_url);
  if (!coords) {
    continue;
  }

  const reviewPath = path.join(rootDir, place.reviews_path);
  const reviews = JSON.parse(await readFile(reviewPath, "utf8"));
  const reviewCount = reviews.length;
  totalReviews += reviewCount;

  const themeCounts = {
    waiting: 0,
    communication: 0,
    process: 0,
    languageDiscrimination: 0,
  };
  const snippetBuckets = {
    waiting: [],
    communication: [],
    process: [],
    languageDiscrimination: [],
  };
  let lowStarCount = 0;
  let starSum = 0;
  let starCount = 0;

  for (const review of reviews) {
    const text = String(review.review_text || "");
    const hits = classifyReview(text);
    const starRating = Number(review.star_rating);

    if (Number.isFinite(starRating)) {
      starSum += starRating;
      starCount += 1;
      if (starRating <= 2) {
        lowStarCount += 1;
      }
    }

    for (const key of Object.keys(themeCounts)) {
      if (!hits[key]) {
        continue;
      }

      themeCounts[key] += 1;

      if (snippetBuckets[key].length >= 2) {
        continue;
      }

      const sanitized = sanitizeSnippet(text);
      if (!sanitized) {
        continue;
      }

      if (starRating > 3 && snippetBuckets[key].length > 0) {
        continue;
      }

      snippetBuckets[key].push({
        text: sanitized,
        star_rating: Number.isFinite(starRating) ? starRating : null,
      });
    }
  }

  const metrics = Object.fromEntries(
    Object.entries(themeCounts).map(([key, count]) => [key, reviewCount > 0 ? count / reviewCount : 0]),
  );

  const qualityFlags = [];
  if (!isInsideLowerSaxony(coords.lat, coords.lon)) {
    qualityFlags.push("outside_lower_saxony");
  }
  if (coords.coordMismatch) {
    qualityFlags.push("coord_mismatch");
  }
  if (reviewCount < 25) {
    qualityFlags.push("low_sample");
  }

  clinics.push({
    place_id: place.place_id,
    clinic_name: place.place_name,
    resolved_name: placeConfig?.resolved_name ?? null,
    city: extractCity(place.place_name),
    lat: coords.lat,
    lon: coords.lon,
    review_count: reviewCount,
    declared_review_total: place.declared_review_total ?? null,
    capture_status: place.status,
    low_star_share: starCount > 0 ? lowStarCount / starCount : 0,
    avg_star: starCount > 0 ? starSum / starCount : null,
    metrics,
    top_themes: getTopThemes(metrics),
    snippets: snippetBuckets,
    quality_flags: qualityFlags,
  });
}

clinics.sort((left, right) => right.review_count - left.review_count);

const output = {
  generatedAt: new Date().toISOString(),
  source: {
    captureSummary: path.relative(websiteDir, captureSummaryPath),
    placeUrls: path.relative(websiteDir, placeUrlsPath),
  },
  sourceSummary: {
    totalClinics: clinics.length,
    totalReviews,
  },
  clinics,
};

await mkdir(path.dirname(outPath), { recursive: true });
await writeFile(outPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");

console.log(`Wrote ${clinics.length} clinics to ${outPath}`);
