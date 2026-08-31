import { useEffect, useState, useCallback } from "react";
import api from "../api";
import Loader from "../components/Loader";

const TABS = ["Overview", "Sources", "Verification", "Settings", "Pending Approval", "Developers & API Keys", "Audit Log", "Users"];

export default function Admin() {
  const [tab, setTab] = useState("Overview");
  const [toast, setToast] = useState("");
  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3500); };
  return (
    <div className="admin-page">
      <div className="admin-title">Admin</div>
      <div className="admin-tabs">
        {TABS.map((t) => <button key={t} className={`admin-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {tab === "Overview" && <Overview showToast={showToast} />}
      {tab === "Sources" && <Sources showToast={showToast} />}
      {tab === "Verification" && <VerificationLayers showToast={showToast} />}
      {tab === "Settings" && <SettingsTab showToast={showToast} />}
      {tab === "Pending Approval" && <PendingApproval showToast={showToast} />}
      {tab === "Developers & API Keys" && <DevelopersAndKeys showToast={showToast} />}
      {tab === "Audit Log" && <AuditLog />}
      {tab === "Users" && <UsersTab showToast={showToast} />}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function Overview({ showToast }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [ingestionStatus, setIngestionStatus] = useState("idle");

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/stats").then((res) => setStats(res.data)).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const pollIngestionStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/admin/actions/ingestion-status");
        setIngestionStatus(res.data.status);
        if (res.data.status !== "running") {
          clearInterval(interval); setBusy(false);
          showToast(res.data.status === "error" ? `Ingestion failed: ${res.data.last_result?.detail || "unknown error"}` : `Ingestion done: ${res.data.last_result?.stories_created ?? 0} stories created`);
          load();
        }
      } catch { clearInterval(interval); setBusy(false); }
    }, 4000);
  }, [load, showToast]);

  const runIngestion = async () => {
    setBusy(true); setIngestionStatus("running");
    try { await api.post("/admin/actions/run-ingestion"); showToast("Ingestion started - this can take a few minutes"); pollIngestionStatus(); }
    catch (err) { setBusy(false); showToast(err.friendlyMessage || "Couldn't start ingestion"); }
  };

  const sendEmailsNow = async () => {
    if (!confirm("Send the latest approved edition to all eligible real users now? This bypasses the normal send-time window but will not send the same edition twice to a user.")) return;
    setBusy(true);
    try {
      const res = await api.post("/admin/actions/send-emails-now", null, { timeout: 6 * 60 * 1000 });
      showToast(`Approved edition emails: ${res.data.sent ?? 0} sent, ${res.data.failed ?? 0} failed, ${res.data.skipped ?? 0} skipped`);
      load();
    } catch (err) { showToast(err.friendlyMessage || "Sending failed"); }
    finally { setBusy(false); }
  };

  const sendTestEmail = async () => {
    setBusy(true);
    try { const res = await api.post("/admin/actions/send-test-email", null, { timeout: 60000 }); showToast(res.data.detail || "Test email sent"); }
    catch (err) { showToast(err.friendlyMessage || "Test send failed"); }
    finally { setBusy(false); }
  };

  if (loading) return <Loader text="Loading stats..." />;
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
        <ModeBadge label="Scheduling" value={stats.scheduling_mode === "auto" ? "Automatic" : "Manual"} tone={stats.scheduling_mode === "auto" ? "ok" : "warn"} />
        <ModeBadge label="Human approval" value={stats.require_human_approval_all ? "Required for all" : "Not required"} tone={stats.require_human_approval_all ? "ok" : "warn"} />
        <ModeBadge label="Verification" value={stats.skip_all_verification ? "SKIPPED (danger)" : "Active"} tone={stats.skip_all_verification ? "danger" : "ok"} />
        {stats.testing_mode && <ModeBadge label="Mode" value="TESTING MODE" tone="warn" />}
      </div>
      <div className="stat-grid">
        <Stat label="Total users" value={stats.total_users} />
        <Stat label="Onboarded" value={stats.onboarded_users} />
        <Stat label="Today's stories" value={stats.todays_stories} />
        <Stat label="Pending approval" value={stats.pending_approval} />
        <Stat label="All approved news" value={stats.approved_total} />
        <Stat label="Approved today" value={stats.approved_today} />
        <Stat label="Active sources" value={stats.active_sources} />
        <Stat label="High-risk sources" value={stats.high_risk_sources} />
        <Stat label="Sources w/ errors" value={stats.sources_with_errors} />
        <Stat label="Emails sent today" value={stats.emails_sent_today} />
        <Stat label="Developer accounts" value={stats.developer_accounts} />
        <Stat label="Active API keys" value={stats.active_api_keys} />
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button className="btn-secondary" onClick={runIngestion} disabled={busy}>{ingestionStatus === "running" ? "Ingesting... (this can take a few minutes)" : "Run ingestion now"}</button>
        <button className="btn-secondary" onClick={sendEmailsNow} disabled={busy}>{busy ? "Working..." : "Send latest approved news now (real users)"}</button>
        <button className="btn-secondary" onClick={sendTestEmail} disabled={busy}>{busy ? "Working..." : "Send TEST email (safe, to test address only)"}</button>
      </div>
    </div>
  );
}

function ModeBadge({ label, value, tone }) {
  const colors = { ok: "#2e7d4f", warn: "#b8442f", danger: "#c0392b" };
  return <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#fff", border: "1px solid var(--border)", borderRadius: 20, padding: "6px 14px", fontSize: 12.5 }}><span style={{ color: "var(--ink-faint)" }}>{label}:</span><span style={{ fontWeight: 700, color: colors[tone] || "#333" }}>{value}</span></div>;
}
function Stat({ label, value }) { return <div className="stat-card"><div className="stat-value">{value}</div><div className="stat-label">{label}</div></div>; }

// The remaining admin tabs/components are intentionally preserved from the existing application.
