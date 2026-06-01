import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const benchmarkDir = path.join(repoRoot, "analysis/llm/benchmark");
const benchmarkBaseName = "benchmark_v1_120";
const baseFileName = `${benchmarkBaseName}_labled.json`;
const reviewedPattern = new RegExp(`^${benchmarkBaseName}_reviewed_.+\\.json$`);
const workingFileName = `${benchmarkBaseName}_working.json`;
const envPaths = [path.join(repoRoot, "scripts/.env"), path.join(repoRoot, ".env")];

const LABEL_GROUPS = [
  {
    title: "Access",
    labels: [
      ["access.appointments", "Terminvergabe, Terminorganisation, Schwierigkeit einen Termin zu bekommen"],
      ["access.waiting", "Wartezeiten vor Behandlung, Untersuchung, Aufnahme oder Entlassung"],
      ["access.reachability", "Telefonische oder digitale Erreichbarkeit, Rückrufe, Kontaktaufnahme"],
      ["access.navigation", "Orientierung im Haus, Wegfindung, Auffindbarkeit von Bereichen"],
    ],
  },
  {
    title: "Admin",
    labels: [
      ["admin.registration", "Anmeldung, Aufnahme, Entlassungsformalitäten, administrative Abwicklung"],
      ["admin.paperwork", "Formulare, Dokumente, Bescheinigungen, bürokratische Unterlagen"],
      ["admin.costs", "Kosten, Abrechnung, finanzielle Belastung, unklare Gebühren"],
      ["admin.privacy", "Datenschutz, Vertraulichkeit, Preisgabe persönlicher Informationen"],
    ],
  },
  {
    title: "Communication",
    labels: [
      ["communication.communication", "Allgemeiner Kommunikationsstil, Rückmeldungen, Gesprächsbereitschaft"],
      ["communication.explanation", "Medizinische Erklärungen, Aufklärung, verständliche Erläuterung"],
      ["communication.information", "Organisatorische Informationen zu Ablauf, Zuständigkeiten und nächsten Schritten"],
      ["communication.decisions", "Einbezug in Entscheidungen, Mitsprache, Zustimmung"],
    ],
  },
  {
    title: "Staff",
    labels: [
      ["staff.friendliness", "Freundlichkeit, Höflichkeit, netter Umgang"],
      ["staff.empathy", "Mitgefühl, menschliche Zuwendung, Verständnis"],
      ["staff.respect", "Respektvoller oder abwertender Umgang, Würde, Tonfall"],
      ["staff.seriousness", "Ob Beschwerden, Schmerzen oder Sorgen ernst genommen wurden"],
    ],
  },
  {
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
    title: "Coordination",
    labels: [
      ["coordination.coordination", "Abstimmung zwischen Stationen, Teams, Fachbereichen, Übergaben"],
      ["coordination.discharge", "Entlassung, Entlassungsorganisation, Vorbereitung der Entlassung"],
      ["coordination.followup", "Nachsorge, Anschlussversorgung, weitere Schritte nach der Behandlung"],
    ],
  },
  {
    title: "Environment",
    labels: [
      ["environment.cleanliness", "Sauberkeit, Hygienezustand von Zimmer, Bad, Bett oder Station"],
      ["environment.facilities", "Ausstattung, Zimmer, Gebäudezustand, Lärm, Komfort"],
      ["environment.food", "Essen, Getränke, Verpflegung"],
      ["environment.support", "Praktische Unterstützung, Hilfe im Alltag, Grundpflege"],
    ],
  },
  {
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

const LABEL_GUIDE = LABEL_GROUPS.map(
  (group) =>
    `${group.title}:\n${group.labels.map(([label, description]) => `- ${label}: ${description}`).join("\n")}`,
).join("\n\n");

function getReviewedFiles() {
  if (!fs.existsSync(benchmarkDir)) {
    return [];
  }

  return fs
    .readdirSync(benchmarkDir)
    .filter((fileName) => reviewedPattern.test(fileName))
    .sort();
}

function getLatestBenchmarkFileName() {
  const workingPath = path.join(benchmarkDir, workingFileName);
  if (fs.existsSync(workingPath)) {
    return workingFileName;
  }

  const reviewedFiles = getReviewedFiles();
  if (reviewedFiles.length > 0) {
    return reviewedFiles[reviewedFiles.length - 1];
  }

  return baseFileName;
}

function readBenchmarkFile(fileName) {
  const filePath = path.join(benchmarkDir, fileName);
  const raw = fs.readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

function formatUtcTimestamp(date = new Date()) {
  const iso = date.toISOString();
  return iso.replace(/:/g, "-").replace(/\.\d{3}Z$/, "Z");
}

function normalizeRecord(record) {
  return {
    ...record,
    ai_review: {
      status: "missing",
      model: "gpt-4.1-mini",
      prompt_version: "benchmark_review_v1",
      checked_at: null,
      verdict: null,
      summary: "",
      suggested_additions: [],
      suggested_removals: [],
      critical_spans: [],
      raw_recommendation_notes: "",
      error_message: "",
      ...(record.ai_review ?? {}),
    },
  };
}

function normalizeBenchmarkData(data) {
  const records = Object.fromEntries(
    Object.entries(data.records || {}).map(([reviewId, record]) => [reviewId, normalizeRecord(record)]),
  );

  return {
    ...data,
    working_file_role: data.working_file_role || (data.saved_at ? "reviewed_snapshot" : "working"),
    working_saved_at: data.working_saved_at || data.saved_at || null,
    ai_review_model: data.ai_review_model || "gpt-4.1-mini",
    ai_review_prompt_version: data.ai_review_prompt_version || "benchmark_review_v1",
    records,
  };
}

function readApiKey() {
  if (process.env.OPENAI_API_KEY) {
    return process.env.OPENAI_API_KEY;
  }

  for (const envPath of envPaths) {
    if (!fs.existsSync(envPath)) {
      continue;
    }

    const raw = fs.readFileSync(envPath, "utf-8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }
      if (trimmed.startsWith("OPENAI_API_KEY=")) {
        return trimmed.slice("OPENAI_API_KEY=".length);
      }
    }
  }

  return null;
}

function buildReviewCheckMessages(body) {
  const prompt = `
Du überprüfst bestehende Benchmark-Labels für eine deutsche Krankenhausbewertung.

Deine Aufgabe:
- prüfe, ob die aktuellen Benchmark-Labels textnah und plausibel sind
- empfehle Ergänzungen nur, wenn sie klar im Text gestützt sind
- empfehle Entfernungen nur, wenn ein gesetztes Label textlich schwach oder unpassend wirkt
- wenn alles im Wesentlichen stimmig ist, gib verdict = "ok"
- wenn Änderungen sinnvoll erscheinen, gib verdict = "consider_changes"

Labelkatalog:
${LABEL_GUIDE}

Aktuelle Benchmark-Labels:
- problem_labels: ${JSON.stringify(body.benchmark_labels?.problem_labels ?? [])}
- strength_labels: ${JSON.stringify(body.benchmark_labels?.strength_labels ?? [])}

Modell-Vorschlag zur Referenz:
- problem_labels: ${JSON.stringify(body.model_prelabels?.problem_labels ?? [])}
- strength_labels: ${JSON.stringify(body.model_prelabels?.strength_labels ?? [])}

Wichtige Regeln:
- nutze nur Labels aus dem Katalog
- bewerte nur anhand des Reviewtexts
- keine Sternbewertung als Grundlage
- critical_spans sollen kurze wörtliche oder sinngenahe Ausschnitte sein, die deine Kritik stützen
- wenn keine Ergänzungen oder Entfernungen nötig sind, gib leere Listen zurück
- antworte ausschließlich als JSON mit den Feldern:
  verdict, summary, suggested_additions, suggested_removals, critical_spans, raw_recommendation_notes

Review:
${body.review_text}
`.trim();

  return [
    {
      role: "system",
      content: "You review existing structured labels for a German hospital review and respond only with valid JSON.",
    },
    {
      role: "user",
      content: prompt,
    },
  ];
}

async function fetchReviewCheck(body) {
  const apiKey = readApiKey();
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY not found in environment or scripts/.env.");
  }

  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4.1-mini",
      response_format: { type: "json_object" },
      messages: buildReviewCheckMessages(body),
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI review check failed: ${errorText}`);
  }

  const payload = await response.json();
  const content = payload.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error("OpenAI review check returned empty content.");
  }

  const parsed = JSON.parse(content);
  return {
    status: "ready",
    model: "gpt-4.1-mini",
    prompt_version: "benchmark_review_v1",
    checked_at: new Date().toISOString(),
    verdict: parsed.verdict === "consider_changes" ? "consider_changes" : "ok",
    summary: parsed.summary || "",
    suggested_additions: Array.isArray(parsed.suggested_additions) ? parsed.suggested_additions : [],
    suggested_removals: Array.isArray(parsed.suggested_removals) ? parsed.suggested_removals : [],
    critical_spans: Array.isArray(parsed.critical_spans) ? parsed.critical_spans : [],
    raw_recommendation_notes: parsed.raw_recommendation_notes || "",
    error_message: "",
  };
}

async function readJsonBody(req) {
  const chunks = [];

  for await (const chunk of req) {
    chunks.push(chunk);
  }

  const body = Buffer.concat(chunks).toString("utf-8");
  return JSON.parse(body);
}

function withJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "benchmark-review-api",
      configureServer(server) {
        server.middlewares.use("/api/benchmark/load", (req, res, next) => {
          if (req.method !== "GET") {
            next();
            return;
          }

          try {
            const fileName = getLatestBenchmarkFileName();
            const data = normalizeBenchmarkData(readBenchmarkFile(fileName));
            withJson(res, 200, {
              fileName,
              data,
              availableFiles: [baseFileName, workingFileName, ...getReviewedFiles()],
            });
          } catch (error) {
            withJson(res, 500, { error: error.message });
          }
        });

        server.middlewares.use("/api/benchmark/autosave", async (req, res, next) => {
          if (req.method !== "POST") {
            next();
            return;
          }

          try {
            const body = await readJsonBody(req);
            if (!body || typeof body !== "object" || !body.data) {
              withJson(res, 400, { error: "Missing benchmark payload." });
              return;
            }

            const workingSavedAt = new Date().toISOString();
            const sourceFile = body.sourceFile || getLatestBenchmarkFileName();
            const nextPayload = normalizeBenchmarkData({
              ...body.data,
              working_saved_at: workingSavedAt,
              working_file_role: "working",
              source_file: sourceFile,
            });

            fs.mkdirSync(benchmarkDir, { recursive: true });
            fs.writeFileSync(
              path.join(benchmarkDir, workingFileName),
              JSON.stringify(nextPayload, null, 2),
              "utf-8",
            );

            withJson(res, 200, {
              fileName: workingFileName,
              workingSavedAt,
            });
          } catch (error) {
            withJson(res, 500, { error: error.message });
          }
        });

        server.middlewares.use("/api/benchmark/save", async (req, res, next) => {
          if (req.method !== "POST") {
            next();
            return;
          }

          try {
            const body = await readJsonBody(req);
            if (!body || typeof body !== "object" || !body.data) {
              withJson(res, 400, { error: "Missing benchmark payload." });
              return;
            }

            const savedAt = new Date().toISOString();
            const fileTimestamp = formatUtcTimestamp(new Date());
            const reviewedFileName = `${benchmarkBaseName}_reviewed_${fileTimestamp}.json`;
            const sourceFile = body.sourceFile || getLatestBenchmarkFileName();
            const nextPayload = normalizeBenchmarkData({
              ...body.data,
              saved_at: savedAt,
              working_saved_at: savedAt,
              working_file_role: "reviewed_snapshot",
              source_file: sourceFile,
            });

            fs.mkdirSync(benchmarkDir, { recursive: true });
            fs.writeFileSync(
              path.join(benchmarkDir, reviewedFileName),
              JSON.stringify(nextPayload, null, 2),
              "utf-8",
            );

            withJson(res, 200, {
              fileName: reviewedFileName,
              savedAt,
            });
          } catch (error) {
            withJson(res, 500, { error: error.message });
          }
        });

        server.middlewares.use("/api/benchmark/review-check", async (req, res, next) => {
          if (req.method !== "POST") {
            next();
            return;
          }

          try {
            const body = await readJsonBody(req);
            if (!body?.review_id || !body?.review_text || !body?.benchmark_labels) {
              withJson(res, 400, { error: "Missing review-check payload." });
              return;
            }

            const aiReview = await fetchReviewCheck(body);
            withJson(res, 200, { ai_review: aiReview });
          } catch (error) {
            withJson(res, 500, {
              ai_review: {
                status: "error",
                model: "gpt-4.1-mini",
                prompt_version: "benchmark_review_v1",
                checked_at: new Date().toISOString(),
                verdict: null,
                summary: "",
                suggested_additions: [],
                suggested_removals: [],
                critical_spans: [],
                raw_recommendation_notes: "",
                error_message: error.message,
              },
              error: error.message,
            });
          }
        });
      },
    },
  ],
  resolve: {
    alias: {
      react: path.resolve(repoRoot, "website/node_modules/react"),
      "react-dom": path.resolve(repoRoot, "website/node_modules/react-dom"),
      "react-refresh": path.resolve(repoRoot, "website/node_modules/react-refresh"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 4174,
  },
});
