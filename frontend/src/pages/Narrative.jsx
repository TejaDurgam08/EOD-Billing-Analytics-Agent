import React, { useEffect, useState } from "react";
import { useSelected } from "../App.jsx";
import { getNarrative } from "../api.js";

export default function Narrative() {
  const selected = useSelected();
  const [narrative, setNarrative] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selected) return;
    setNarrative(null);
    setError(null);
    getNarrative(selected.clinic_id, selected.log_date)
      .then(setNarrative)
      .catch((err) => setError(err.message));
  }, [selected]);

  if (!selected) return null;
  if (error) return <div className="error-box">{error}</div>;
  if (!narrative) return <div className="loading">Generating…</div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">
            AI Narrative Summary <span className="narrative-badge">AI Suggested</span>
          </h1>
          <div className="page-subtitle">
            Generated from today's reconciliation — {selected.clinic_id}
          </div>
        </div>
      </div>

      <div className="narrative-grid">
        <div className="narrative-panel">
          <div className="narrative-meta">Sent to clinic owner — WhatsApp draft</div>
          <div className="narrative-text">{narrative.narrative}</div>
          <div className="narrative-status">
            {narrative.grounded ? "✓ Grounded" : "Ungrounded"}
          </div>
          {narrative.notes.length > 0 && (
            <div style={{ marginTop: 10, fontSize: 12, color: "#4a8f66" }}>
              {narrative.notes.map((n, i) => (
                <div key={i}>{n}</div>
              ))}
            </div>
          )}
        </div>

        <div className="card trace-panel">
          <div className="section-title">Traced Figures</div>
          <div className="trace-note">
            Every number above maps to the deterministic report — this is what gets
            auto-checked.
          </div>
          {narrative.traced_figures.map((f) => (
            <div className="trace-row" key={f.source_field}>
              <span className="trace-value">{f.value_display}</span>
              <span className="trace-field">{f.source_field}</span>
            </div>
          ))}
          {narrative.traced_figures.length === 0 && (
            <div className="empty-box">No figures traced in this narrative.</div>
          )}
        </div>
      </div>
    </div>
  );
}
