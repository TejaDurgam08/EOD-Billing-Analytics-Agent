import React, { useEffect, useState } from "react";
import { useSelected } from "../App.jsx";
import { getReports, formatRupees } from "../api.js";

export default function Reconciliation() {
  const selected = useSelected();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    setError(null);
    getReports(selected.clinic_id, selected.log_date)
      .then((data) => setReport(data.reconciliation))
      .catch((err) => setError(err.message));
  }, [selected]);

  if (!selected) return null;
  if (error) return <div className="error-box">{error}</div>;
  if (!report) return <div className="loading">Loading…</div>;

  const collectionRate =
    report.total_billed_paise > 0
      ? Math.round((report.total_collected_paise / report.total_billed_paise) * 100)
      : null;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">EOD Reconciliation</h1>
          <div className="page-subtitle">{report.clinic_id}</div>
        </div>
        <div className="date-pill">{selected.log_date}</div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Total Billed</div>
          <div className="stat-value">{formatRupees(report.total_billed_paise)}</div>
          <div className="stat-sub">{report.total_visits} visits</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Collected</div>
          <div className="stat-value">{formatRupees(report.total_collected_paise)}</div>
          <div className="stat-sub positive">
            {collectionRate !== null ? `${collectionRate}% of billed` : "—"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Outstanding</div>
          <div className="stat-value">{formatRupees(report.total_outstanding_paise)}</div>
          <div className="stat-sub warn">{report.outstanding_visit_count} pending visits</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Refunds</div>
          <div className="stat-value">{formatRupees(report.total_refunds_paise)}</div>
          <div className="stat-sub">{report.refund_count} refund(s)</div>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Payment Mode Breakdown</div>
        <table>
          <thead>
            <tr>
              <th>Mode</th>
              <th>Billed</th>
              <th>Collected</th>
              <th>Outstanding</th>
              <th>Refunds</th>
              <th>Visits</th>
            </tr>
          </thead>
          <tbody>
            {report.by_payment_mode.map((row) => (
              <tr key={row.payment_mode}>
                <td style={{ textTransform: "capitalize", fontWeight: 600 }}>{row.payment_mode}</td>
                <td>{formatRupees(row.billed_paise)}</td>
                <td>{formatRupees(row.collected_paise)}</td>
                <td>{formatRupees(row.outstanding_paise)}</td>
                <td>{formatRupees(row.refunds_paise)}</td>
                <td>{row.visit_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report.rejected_rows.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-title">Rejected Rows ({report.rejected_rows.length})</div>
          <table>
            <thead>
              <tr>
                <th>Row #</th>
                <th>Visit ID</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {report.rejected_rows.map((r) => (
                <tr key={r.index}>
                  <td>{r.index}</td>
                  <td>{r.visit_id || "—"}</td>
                  <td>{r.errors.join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
