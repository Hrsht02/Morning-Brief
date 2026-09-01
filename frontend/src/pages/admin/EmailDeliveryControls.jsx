import { useState } from "react";
import api from "../../api";

export default function EmailDeliveryControls({ onResult }) {
  const [busy, setBusy] = useState(false);
  const run = async (action, format) => {
    setBusy(true);
    try { const { data } = await action(); onResult?.(format(data)); }
    catch (error) { onResult?.(error.friendlyMessage || "Email operation failed"); }
    finally { setBusy(false); }
  };
  return <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
    <button className="btn-secondary" disabled={busy} onClick={() => { if (!confirm("Send the latest approved edition to all eligible real users now?")) return; run(() => api.post("/admin/actions/send-emails-now", null, { timeout: 6 * 60 * 1000 }), d => `Approved edition emails: ${d.sent ?? 0} sent, ${d.failed ?? 0} failed, ${d.skipped ?? 0} skipped`); }}>{busy ? "Working..." : "Send latest approved news now (real users)"}</button>
    <button className="btn-secondary" disabled={busy} onClick={() => run(() => api.post("/admin/actions/send-test-email", null, { timeout: 60000 }), d => d.detail || "Test email sent")}>{busy ? "Working..." : "Send TEST email"}</button>
    <button className="btn-secondary" disabled={busy} onClick={() => run(() => api.post("/admin/actions/test-automatic-email", null, { timeout: 60000 }), d => d.status === "ok" ? `Automatic scheduler test sent to ${d.test_recipient} (${d.stories_sent} stories). No subscriber was emailed.` : `Automatic scheduler would not send now: ${d.reason || d.detail || "no eligible delivery"}`)}>{busy ? "Testing scheduler..." : "Test automatic email"}</button>
  </div>;
}
