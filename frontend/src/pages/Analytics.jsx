import React, { useEffect, useState } from "react";
import { useSelected } from "../App.jsx";
import { getReports, formatRupees } from "../api.js";

export default function Analytics() {
  const selected = useSelected();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    setError(null);
    getReports(selected.clinic_id, selected.log_date)
      .then((data) => setReport(data.analytics))
      .catch((err) => setError(err.message));
  }, [selected]);

  if (!selected) return null;
  if (error) return <div className="error-box">{error}</div>;
  if (!report) return <div className="loading">Loading…</div>;

  const maxRevenue = Math.max(1, ...report.revenue_by_hour.map((h) => h.revenue_paise));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <div className="page-subtitle">{report.clinic_id}</div>
        </div>
        <div className="date-pill">{selected.log_date}</div>
      </div>

      <div className="card">
        <div className="section-title">Revenue by Hour of Day</div>
        {report.peak_hour && (
          <div className="peak-callout">
            Peak: {report.peak_hour.label} — {formatRupees(report.peak_hour.revenue_paise)}
          </div>
        )}
        {report.revenue_by_hour.length === 0 ? (
          <div className="empty-box">No revenue recorded for this day.</div>
        ) : (
          <div className="bar-chart">
            {report.revenue_by_hour.map((h) => (
              <div className="bar-col" key={h.hour_start}>
                <div
                  className={`bar${report.peak_hour && h.hour_start === report.peak_hour.hour_start ? " peak" : ""}`}
                  style={{ height: `${Math.max(6, (h.revenue_paise / maxRevenue) * 100)}%` }}
                  title={`${h.label}: ${formatRupees(h.revenue_paise)}`}
                />
                <div className="bar-hour-label">{h.label.split("-")[0]}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="analytics-grid">
        <div className="card">
          <div className="section-title">Top Medicines — by Quantity</div>
          {report.top_drugs_by_qty.length === 0 ? (
            <div className="empty-box">No medicine sales today.</div>
          ) : (
            <ul className="rank-list">
              {report.top_drugs_by_qty.map((d, i) => (
                <li key={d.drug_name}>
                  <span className="rank-num">{i + 1}</span>
                  <span className="rank-name">{d.drug_name}</span>
                  <span className="rank-value">{d.qty} units</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <div className="section-title">Top Medicines — by Revenue</div>
          {report.top_drugs_by_revenue.length === 0 ? (
            <div className="empty-box">No medicine sales today.</div>
          ) : (
            <ul className="rank-list">
              {report.top_drugs_by_revenue.map((d, i) => (
                <li key={d.drug_name}>
                  <span className="rank-num">{i + 1}</span>
                  <span className="rank-name">{d.drug_name}</span>
                  <span className="rank-value">{formatRupees(d.revenue_paise)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
