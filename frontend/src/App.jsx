import React, { useEffect, useState, useCallback } from "react";
import { Routes, Route, Navigate, Outlet, useOutletContext } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import Reconciliation from "./pages/Reconciliation.jsx";
import Analytics from "./pages/Analytics.jsx";
import Narrative from "./pages/Narrative.jsx";
import { listIngestions } from "./api.js";

function Layout() {
  const [ingestions, setIngestions] = useState([]);
  const [selected, setSelected] = useState(null); // { clinic_id, log_date }
  const [loadError, setLoadError] = useState(null);

  const refresh = useCallback(() => {
    listIngestions()
      .then((rows) => {
        setIngestions(rows);
        if (rows.length > 0 && !selected) {
          setSelected({ clinic_id: rows[0].clinic_id, log_date: rows[0].log_date });
        }
      })
      .catch((err) => setLoadError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        {loadError && <div className="error-box">Couldn't reach the API: {loadError}</div>}
        {!loadError && ingestions.length === 0 && (
          <div className="empty-box">
            No billing logs ingested yet. POST a daily log to <code>/api/ingest</code>{" "}
            (see <code>backend/seed_sample_data.py</code> to load the sample dataset).
          </div>
        )}
        {ingestions.length > 0 && (
          <>
            <div className="picker-row">
              {ingestions.map((row) => (
                <button
                  key={`${row.clinic_id}-${row.log_date}`}
                  className={`picker-btn${
                    selected && selected.log_date === row.log_date && selected.clinic_id === row.clinic_id
                      ? " active"
                      : ""
                  }`}
                  onClick={() => setSelected({ clinic_id: row.clinic_id, log_date: row.log_date })}
                >
                  {row.log_date}
                </button>
              ))}
            </div>
            <Outlet context={{ selected }} />
          </>
        )}
      </div>
    </div>
  );
}

export function useSelected() {
  return useOutletContext().selected;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/reconciliation" replace />} />
        <Route path="/reconciliation" element={<Reconciliation />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/narrative" element={<Narrative />} />
      </Route>
    </Routes>
  );
}
