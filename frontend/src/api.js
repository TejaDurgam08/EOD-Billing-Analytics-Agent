const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function handle(resp) {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return resp.json();
}

export async function listIngestions() {
  const resp = await fetch(`${API_BASE}/api/ingestions`);
  return handle(resp);
}

export async function ingestLog(logDate, payload) {
  const resp = await fetch(`${API_BASE}/api/ingest?log_date=${encodeURIComponent(logDate)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(resp);
}

export async function getReports(clinicId, logDate) {
  const resp = await fetch(`${API_BASE}/api/reports/${clinicId}/${logDate}`);
  return handle(resp);
}

export async function getNarrative(clinicId, logDate) {
  const resp = await fetch(`${API_BASE}/api/reports/${clinicId}/${logDate}/narrative`);
  return handle(resp);
}

export function formatRupees(paise) {
  const rupees = paise / 100;
  const whole = Number.isInteger(rupees);
  return `₹${rupees.toLocaleString("en-IN", {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}
