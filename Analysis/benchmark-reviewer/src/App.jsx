import { useEffect, useMemo, useRef, useState } from "react";

import { AI_REVIEW_STATUS, createEmptyAiReview, ensureAiReview } from "./aiReviewSchema.js";
import { LABEL_DESCRIPTIONS, LABEL_GROUPS } from "./labelCatalog.js";

function labelChipClass(kind) {
  return kind === "problem" ? "pill pill--problem" : "pill pill--strength";
}

function cloneData(data) {
  return JSON.parse(JSON.stringify(data));
}

function formatBoolean(value) {
  return value ? "ja" : "nein";
}

function formatTimestamp(value) {
  if (!value) {
    return "noch nicht gespeichert";
  }

  return value;
}

function formatStatusLabel(value) {
  if (value === "reviewed_by_user") {
    return "reviewed";
  }

  return value;
}

function canFinalize(records) {
  const reviewIds = Object.keys(records);
  return reviewIds.length > 0 && reviewIds.every((reviewId) => records[reviewId].benchmark_status === "reviewed_by_user");
}

function getLatestVisibleIndex(filteredIds, activeId) {
  const found = filteredIds.indexOf(activeId);
  return found >= 0 ? found : 0;
}

function toggleLabel(records, reviewId, listKey, label) {
  const next = cloneData(records);
  const values = next[reviewId].benchmark_labels[listKey];
  const idx = values.indexOf(label);

  if (idx >= 0) {
    values.splice(idx, 1);
  } else {
    values.push(label);
    values.sort();
  }

  const aiReview = ensureAiReview(next[reviewId]);
  if (aiReview.status === AI_REVIEW_STATUS.READY) {
    next[reviewId].ai_review = {
      ...aiReview,
      status: AI_REVIEW_STATUS.STALE,
    };
  } else if (aiReview.status === AI_REVIEW_STATUS.ERROR) {
    next[reviewId].ai_review = {
      ...aiReview,
      status: AI_REVIEW_STATUS.STALE,
      error_message: "",
    };
  } else if (aiReview.status === AI_REVIEW_STATUS.MISSING) {
    next[reviewId].ai_review = aiReview;
  }

  return next;
}

function updateRecordField(records, reviewId, patch) {
  const nextRecord = {
    ...records[reviewId],
    ...patch,
  };
  if (Object.prototype.hasOwnProperty.call(patch, "benchmark_notes") === false && Object.prototype.hasOwnProperty.call(patch, "benchmark_status") === false) {
    const aiReview = ensureAiReview(nextRecord);
    nextRecord.ai_review = aiReview;
  }

  return {
    ...records,
    [reviewId]: nextRecord,
  };
}

function renderLabelPills(labels, kind) {
  if (!labels.length) {
    return <p className="empty-state">Keine Labels gesetzt.</p>;
  }

  return (
    <div className="pill-list">
      {labels.map((label) => (
        <span key={label} className={labelChipClass(kind)} title={LABEL_DESCRIPTIONS[label]}>
          {label}
        </span>
      ))}
    </div>
  );
}

export default function App() {
  const [payload, setPayload] = useState(null);
  const [sourceFile, setSourceFile] = useState(null);
  const [availableFiles, setAvailableFiles] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [bucketFilter, setBucketFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [saveMessage, setSaveMessage] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isAutoSaving, setIsAutoSaving] = useState(false);
  const [aiBusyId, setAiBusyId] = useState(null);
  const autosaveTimeoutRef = useRef(null);
  const autosaveEnabledRef = useRef(false);
  const aiRequestedRef = useRef(new Set());

  useEffect(() => {
    fetch("/api/benchmark/load")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Benchmark-Datei konnte nicht geladen werden.");
        }
        return response.json();
      })
      .then((result) => {
        const normalizedRecords = Object.fromEntries(
          Object.entries(result.data.records).map(([reviewId, record]) => [reviewId, { ...record, ai_review: ensureAiReview(record) }]),
        );
        setPayload({
          ...result.data,
          records: normalizedRecords,
        });
        setSourceFile(result.fileName);
        setAvailableFiles(result.availableFiles || []);
        const firstId = Object.keys(normalizedRecords)[0] || null;
        setSelectedId(firstId);
        autosaveEnabledRef.current = true;
      })
      .catch((caughtError) => {
        setError(caughtError.message);
      });
  }, []);

  const records = payload?.records ?? {};
  const allIds = useMemo(() => Object.keys(records), [records]);

  const filteredIds = useMemo(() => {
    return allIds.filter((reviewId) => {
      const record = records[reviewId];
      if (!record) {
        return false;
      }

      if (bucketFilter !== "all" && record.bucket !== bucketFilter) {
        return false;
      }

      if (statusFilter !== "all" && record.benchmark_status !== statusFilter) {
        return false;
      }

      return true;
    });
  }, [allIds, records, bucketFilter, statusFilter]);

  useEffect(() => {
    if (!selectedId && filteredIds.length > 0) {
      setSelectedId(filteredIds[0]);
      return;
    }

    if (selectedId && filteredIds.length > 0 && !filteredIds.includes(selectedId)) {
      setSelectedId(filteredIds[0]);
    }
  }, [filteredIds, selectedId]);

  const activeRecord = selectedId ? records[selectedId] : null;
  const activeIndex = activeRecord ? getLatestVisibleIndex(filteredIds, selectedId) : 0;
  const reviewedCount = allIds.filter((reviewId) => records[reviewId].benchmark_status === "reviewed_by_user").length;
  const readyForFinalSave = canFinalize(records);
  const reviewedPercent = allIds.length > 0 ? Math.round((reviewedCount / allIds.length) * 100) : 0;

  useEffect(() => {
    if (!payload || !autosaveEnabledRef.current) {
      return undefined;
    }

    if (autosaveTimeoutRef.current) {
      clearTimeout(autosaveTimeoutRef.current);
    }

    autosaveTimeoutRef.current = setTimeout(async () => {
      setIsAutoSaving(true);
      try {
        const response = await fetch("/api/benchmark/autosave", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            sourceFile,
            data: payload,
          }),
        });

        if (!response.ok) {
          throw new Error("Autosave fehlgeschlagen.");
        }

        const result = await response.json();
        setSourceFile(result.fileName);
        setPayload((current) => ({
          ...current,
          working_saved_at: result.workingSavedAt,
          working_file_role: "working",
        }));
        setAvailableFiles((current) => [...new Set([...current, result.fileName])].sort());
      } catch (caughtError) {
        setError(caughtError.message);
      } finally {
        setIsAutoSaving(false);
      }
    }, 700);

    return () => {
      if (autosaveTimeoutRef.current) {
        clearTimeout(autosaveTimeoutRef.current);
      }
    };
  }, [payload, sourceFile]);

  useEffect(() => {
    if (!selectedId || !records[selectedId]) {
      return;
    }

    const currentRecord = records[selectedId];
    const aiReview = ensureAiReview(currentRecord);
    if (aiReview.status !== AI_REVIEW_STATUS.MISSING) {
      return;
    }
    if (aiRequestedRef.current.has(selectedId)) {
      return;
    }

    aiRequestedRef.current.add(selectedId);
    setPayload((current) => ({
      ...current,
      records: updateRecordField(current.records, selectedId, {
        ai_review: {
          ...ensureAiReview(current.records[selectedId]),
          status: AI_REVIEW_STATUS.QUEUED,
          error_message: "",
        },
      }),
    }));
    setAiBusyId(selectedId);

    fetch("/api/benchmark/review-check", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        review_id: selectedId,
        review_text: currentRecord.review_text,
        benchmark_labels: currentRecord.benchmark_labels,
        model_prelabels: currentRecord.model_prelabels,
      }),
    })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || "KI-Prüfung fehlgeschlagen.");
        }
        setPayload((current) => ({
          ...current,
          records: updateRecordField(current.records, selectedId, {
            ai_review: result.ai_review,
          }),
        }));
      })
      .catch((caughtError) => {
        setPayload((current) => ({
          ...current,
          records: updateRecordField(current.records, selectedId, {
            ai_review: {
              ...ensureAiReview(current.records[selectedId]),
              status: AI_REVIEW_STATUS.ERROR,
              checked_at: new Date().toISOString(),
              error_message: caughtError.message,
            },
          }),
        }));
      })
      .finally(() => {
        setAiBusyId((current) => (current === selectedId ? null : current));
      });
  }, [selectedId, records]);

  const handleToggle = (listKey, label) => {
    setPayload((current) => ({
      ...current,
      records: toggleLabel(current.records, selectedId, listKey, label),
    }));
  };

  const handleNotesChange = (event) => {
    const nextValue = event.target.value;
    setPayload((current) => ({
      ...current,
      records: updateRecordField(current.records, selectedId, { benchmark_notes: nextValue }),
    }));
  };

  const handleStatusChange = (event) => {
    const nextValue = event.target.value;
    setPayload((current) => ({
      ...current,
      records: updateRecordField(current.records, selectedId, { benchmark_status: nextValue }),
    }));
  };

  const markReviewed = (status) => {
    setPayload((current) => ({
      ...current,
      records: updateRecordField(current.records, selectedId, { benchmark_status: status }),
    }));
  };

  const runAiReview = async () => {
    if (!selectedId || !activeRecord) {
      return;
    }

    setAiBusyId(selectedId);
    setPayload((current) => ({
      ...current,
      records: updateRecordField(current.records, selectedId, {
        ai_review: {
          ...ensureAiReview(current.records[selectedId]),
          status: AI_REVIEW_STATUS.QUEUED,
          error_message: "",
        },
      }),
    }));

    try {
      const response = await fetch("/api/benchmark/review-check", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          review_id: selectedId,
          review_text: activeRecord.review_text,
          benchmark_labels: activeRecord.benchmark_labels,
          model_prelabels: activeRecord.model_prelabels,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "KI-Prüfung fehlgeschlagen.");
      }
      setPayload((current) => ({
        ...current,
        records: updateRecordField(current.records, selectedId, {
          ai_review: result.ai_review,
        }),
      }));
    } catch (caughtError) {
      setPayload((current) => ({
        ...current,
        records: updateRecordField(current.records, selectedId, {
          ai_review: {
            ...ensureAiReview(current.records[selectedId]),
            status: AI_REVIEW_STATUS.ERROR,
            checked_at: new Date().toISOString(),
            error_message: caughtError.message,
          },
        }),
      }));
    } finally {
      setAiBusyId(null);
    }
  };

  const handleSave = async () => {
    if (!payload || !readyForFinalSave) {
      return;
    }

    setIsSaving(true);
    setSaveMessage("");
    setError("");

    try {
      const response = await fetch("/api/benchmark/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sourceFile,
          data: payload,
        }),
      });

      if (!response.ok) {
        throw new Error("Speichern der Benchmark-Version fehlgeschlagen.");
      }

      const result = await response.json();
      setSourceFile(result.fileName);
      setPayload((current) => ({
        ...current,
        saved_at: result.savedAt,
        working_saved_at: result.savedAt,
        working_file_role: "reviewed_snapshot",
        source_file: sourceFile,
      }));
      setAvailableFiles((current) => [...new Set([...current, result.fileName])].sort());
      setSaveMessage(`Gespeichert als ${result.fileName}`);
    } catch (caughtError) {
      setError(caughtError.message);
    } finally {
      setIsSaving(false);
    }
  };

  const jumpRelative = (delta) => {
    if (!filteredIds.length) {
      return;
    }

    const nextIndex = Math.min(Math.max(activeIndex + delta, 0), filteredIds.length - 1);
    setSelectedId(filteredIds[nextIndex]);
  };

  const jumpToNextUnreviewed = () => {
    const nextId = filteredIds.find((reviewId, idx) => {
      if (idx <= activeIndex) {
        return false;
      }
      return records[reviewId].benchmark_status !== "reviewed_by_user";
    });

    if (nextId) {
      setSelectedId(nextId);
    }
  };

  if (error && !payload) {
    return (
      <main className="reviewer-shell">
        <div className="error-banner">{error}</div>
      </main>
    );
  }

  if (!payload || !activeRecord) {
    return (
      <main className="reviewer-shell">
        <div className="panel">Benchmark-Datei wird geladen…</div>
      </main>
    );
  }

  return (
    <main className="reviewer-shell">
      <header className="reviewer-header">
        <div>
          <h1>Benchmark Reviewer</h1>
          <p>
            Lokales Review-Tool für den Benchmark-Datensatz. Modellvorschläge bleiben sichtbar,
            aber bearbeitet werden nur die eigentlichen Benchmark-Labels.
          </p>
        </div>
        <div className="status-chip-row">
          <span className="status-chip status-chip--accent">{payload.benchmark_name}</span>
          <span className="status-chip">Geladen: {sourceFile}</span>
          <span className="status-chip">Letzter Save: {formatTimestamp(payload.saved_at)}</span>
          <span className="status-chip">Autosave: {formatTimestamp(payload.working_saved_at)}</span>
        </div>
      </header>

      <div className="progress-strip" aria-label="Review-Fortschritt">
        <div className="progress-strip__track">
          <div
            className="progress-strip__fill"
            style={{ width: `${reviewedPercent}%` }}
          />
        </div>
        <div className="progress-strip__meta">
          {reviewedCount} / {allIds.length} reviewed
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="reviewer-grid">
        <aside className="panel">
          <div className="sidebar-section">
            <h2>Fortschritt</h2>
            <div className="metric-grid">
              <div className="metric-card">
                <strong>{reviewedCount}</strong>
                <span>reviewed</span>
              </div>
              <div className="metric-card">
                <strong>{allIds.length}</strong>
                <span>Gesamt</span>
              </div>
              <div className="metric-card">
                <strong>{filteredIds.length}</strong>
                <span>Im aktuellen Filter</span>
              </div>
              <div className="metric-card">
                <strong>{activeIndex + 1}</strong>
                <span>Aktuelle Position</span>
              </div>
            </div>
          </div>

          <div className="sidebar-section filter-stack">
            <h3>Filter</h3>
            <div className="field-stack">
              <label htmlFor="bucket-filter">Bucket</label>
              <select id="bucket-filter" value={bucketFilter} onChange={(event) => setBucketFilter(event.target.value)}>
                <option value="all">Alle</option>
                <option value="negative">negative</option>
                <option value="positive">positive</option>
                <option value="mixed_hard">mixed_hard</option>
              </select>
            </div>
            <div className="field-stack">
              <label htmlFor="status-filter">Status</label>
              <select id="status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">Alle</option>
                <option value="prelabeled">prelabeled</option>
                <option value="reviewed_by_user">reviewed</option>
              </select>
            </div>
          </div>

          <div className="sidebar-section action-stack">
            <h3>Navigation</h3>
            <button type="button" className="secondary-button" onClick={() => jumpRelative(-1)}>
              Vorheriger Review
            </button>
            <button type="button" className="secondary-button" onClick={() => jumpRelative(1)}>
              Nächster Review
            </button>
            <button type="button" className="secondary-button" onClick={jumpToNextUnreviewed}>
              Nächster unreviewed Review
            </button>
            <button type="button" className="primary-button" onClick={handleSave} disabled={isSaving || !readyForFinalSave}>
              {isSaving ? "Speichert..." : "Speichern als neue Benchmark-Version"}
            </button>
            {!readyForFinalSave ? (
              <div className="helper-text">Finaler Snapshot erst möglich, wenn alle Reviews auf reviewed stehen.</div>
            ) : null}
          </div>

          <div className="sidebar-section">
            <h3>Versionen</h3>
            <div className="review-index-list">
              {availableFiles.map((fileName) => (
                <div key={fileName} className="status-chip">
                  {fileName}
                </div>
              ))}
            </div>
          </div>

          <div className="sidebar-section">
            <h3>Reviews</h3>
            <div className="review-index-list">
              {filteredIds.map((reviewId) => {
                const record = records[reviewId];
                return (
                  <button
                    key={reviewId}
                    type="button"
                    className={`review-index-item${reviewId === selectedId ? " is-active" : ""}`}
                    onClick={() => setSelectedId(reviewId)}
                  >
                    <strong>{reviewId}</strong>
                    <small>
                      {record.bucket} · {record.metadata.star_rating ?? "?"} Sterne · {formatStatusLabel(record.benchmark_status)}
                    </small>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <section className="panel">
          <h2>Review</h2>
          <div className="meta-row">
            <span className="meta-pill">{activeRecord.review_id}</span>
            <span className="meta-pill">Bucket: {activeRecord.bucket}</span>
            <span className="meta-pill">Klinik: {activeRecord.metadata.place_id}</span>
            <span className="meta-pill">Sterne: {activeRecord.metadata.star_rating ?? "?"}</span>
            <span className="meta-pill">Likes: {activeRecord.metadata.like_count ?? 0}</span>
            <span className="meta-pill">
              Owner Response: {formatBoolean(activeRecord.metadata.has_owner_response)}
            </span>
          </div>
          <div className="review-text">{activeRecord.review_text}</div>

          <div className="panel panel--subsection">
            <div className="subsection-header">
              <h3>KI-Prüfung</h3>
              <div className="status-chip-row">
                <span className="status-chip">Status: {ensureAiReview(activeRecord).status}</span>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={runAiReview}
                  disabled={aiBusyId === selectedId}
                >
                  {aiBusyId === selectedId ? "Prüft..." : "KI-Prüfung neu ausführen"}
                </button>
              </div>
            </div>
            <p className="helper-text">
              Diese Zweitprüfung ist nur eine Assistenz. Sie ändert keine Labels automatisch.
            </p>
            {ensureAiReview(activeRecord).status === AI_REVIEW_STATUS.QUEUED ? (
              <p className="empty-state">KI-Empfehlung wird gerade erzeugt…</p>
            ) : null}
            {ensureAiReview(activeRecord).status === AI_REVIEW_STATUS.ERROR ? (
              <div className="error-banner">KI-Prüfung fehlgeschlagen: {ensureAiReview(activeRecord).error_message}</div>
            ) : null}
            {ensureAiReview(activeRecord).status === AI_REVIEW_STATUS.READY || ensureAiReview(activeRecord).status === AI_REVIEW_STATUS.STALE ? (
              <div className="ai-review-block">
                <div className="metric-grid">
                  <div className="metric-card">
                    <strong>{ensureAiReview(activeRecord).verdict || "-"}</strong>
                    <span>Verdict</span>
                  </div>
                  <div className="metric-card">
                    <strong>{formatTimestamp(ensureAiReview(activeRecord).checked_at)}</strong>
                    <span>Geprüft</span>
                  </div>
                </div>
                <div className="field-stack">
                  <label>Zusammenfassung</label>
                  <div className="ai-review-text">{ensureAiReview(activeRecord).summary || "Keine Zusammenfassung."}</div>
                </div>
                <div className="suggestion-columns">
                  <div>
                    <h4>Empfohlene Ergänzungen</h4>
                    {renderLabelPills(ensureAiReview(activeRecord).suggested_additions || [], "strength")}
                  </div>
                  <div>
                    <h4>Empfohlene Entfernungen</h4>
                    {renderLabelPills(ensureAiReview(activeRecord).suggested_removals || [], "problem")}
                  </div>
                </div>
                <div className="field-stack">
                  <label>Kritische Textstellen</label>
                  {(ensureAiReview(activeRecord).critical_spans || []).length ? (
                    <ul className="critical-span-list">
                      {ensureAiReview(activeRecord).critical_spans.map((span) => (
                        <li key={span}>{span}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty-state">Keine kritischen Textstellen genannt.</p>
                  )}
                </div>
                <div className="field-stack">
                  <label>Begründung</label>
                  <div className="ai-review-text">
                    {ensureAiReview(activeRecord).raw_recommendation_notes || "Keine Zusatzbegründung."}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <h2>Modellvorschlag und Benchmark-Labels</h2>

          <div className="suggestion-columns">
            <div>
              <h3>Model Prelabels: Problems</h3>
              {renderLabelPills(activeRecord.model_prelabels.problem_labels, "problem")}
            </div>
            <div>
              <h3>Model Prelabels: Strengths</h3>
              {renderLabelPills(activeRecord.model_prelabels.strength_labels, "strength")}
            </div>
          </div>

          <div className="editor-grid">
            <div className="editor-columns">
              <div>
                <h3>Benchmark Problems</h3>
                {LABEL_GROUPS.map((group) => (
                  <div key={`problem-${group.key}`} className="domain-block">
                    <h4>{group.title}</h4>
                    <div className="toggle-grid">
                      {group.labels.map(([label, description]) => {
                        const active = activeRecord.benchmark_labels.problem_labels.includes(label);
                        return (
                          <button
                            key={`problem-${label}`}
                            type="button"
                            className={`toggle-card${active ? " is-active-problem" : ""}`}
                            onClick={() => handleToggle("problem_labels", label)}
                          >
                            <strong>{label}</strong>
                            <span>{description}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div>
                <h3>Benchmark Strengths</h3>
                {LABEL_GROUPS.map((group) => (
                  <div key={`strength-${group.key}`} className="domain-block">
                    <h4>{group.title}</h4>
                    <div className="toggle-grid">
                      {group.labels.map(([label, description]) => {
                        const active = activeRecord.benchmark_labels.strength_labels.includes(label);
                        return (
                          <button
                            key={`strength-${label}`}
                            type="button"
                            className={`toggle-card${active ? " is-active-strength" : ""}`}
                            onClick={() => handleToggle("strength_labels", label)}
                          >
                            <strong>{label}</strong>
                            <span>{description}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="field-stack">
              <label>Review-Status</label>
              <div className="review-action-row">
                <button
                  type="button"
                  className={`primary-button${activeRecord.benchmark_status === "reviewed_by_user" ? " is-reviewed" : ""}`}
                  onClick={() => markReviewed("reviewed_by_user")}
                >
                  Als reviewed markieren
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => markReviewed("prelabeled")}
                >
                  Zurück auf prelabeled
                </button>
                <span className="status-chip">Aktuell: {formatStatusLabel(activeRecord.benchmark_status)}</span>
              </div>
              <div className="helper-text">
                Die finale Benchmark-Version lässt sich erst speichern, wenn alle Reviews reviewed sind.
              </div>
            </div>

            <div className="field-stack">
              <label htmlFor="benchmark-notes">Benchmark-Notizen</label>
              <textarea
                id="benchmark-notes"
                rows="6"
                value={activeRecord.benchmark_notes}
                onChange={handleNotesChange}
                placeholder="Grenzfall, offene Frage oder Begründung für die Korrektur notieren…"
              />
            </div>
          </div>

          {saveMessage ? <div className="save-banner">{saveMessage}</div> : null}
          {isAutoSaving ? <div className="save-banner">Arbeitsstand wird automatisch gespeichert…</div> : null}
        </section>
      </section>
    </main>
  );
}
