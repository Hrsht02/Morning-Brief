import { useState } from "react";
import api from "../api";
import SandboxCheck from "../components/admin/SandboxCheck";

function CheckList({ title, checks = [] }) {
  return <div style={{ marginTop: 18 }}><h3 style={{ fontFamily: "var(--serif)" }}>{title}</h3>{checks.map((c) => <SandboxCheck key={c.name} check={c} />)}</div>;
}

function SuiteSummary({ result }) {
  if (!result) return null;
  const checks = [...(result.health?.checks || []), ...(result.features?.checks || [])];
  const passed = checks.filter((c) => c.passed).length;
  return <div style={{ marginTop: 18, padding: 14, border: "1px solid var(--border)", borderRadius: 10 }}><strong>{result.status === "ready" ? "✓ Sandbox ready" : "✕ Sandbox needs attention"}</strong><div style={{ color: "var(--ink-faint)", fontSize: 13, marginTop: 4 }}>{passed}/{checks.length} readiness checks passed · Automatic email: {result.automatic_email?.would_send ? "WOULD SEND" : "would not send"}</div></div>;
}

function SimulationRows({ users = [] }) {
  return <div style={{ marginTop: 18 }}><h3 style={{ fontFamily: "var(--serif)" }}>Automatic-email simulation</h3>{users.map((u) => <div key={u.user_id} style={{ padding: 10, borderBottom: "1px solid var(--border)", fontSize: 13 }}><strong>User #{u.user_id}</strong> · {u.timezone} · configured {u.configured_send_time} · approved: {u.approved_stories_for_local_date} · selected: {u.selected_story_count} · <strong>{u.would_send ? "WOULD SEND" : `would not send (${u.decision})`}</strong></div>)}</div>;
}

export default function Sandbox() {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (path) => {
    setBusy(true); setError(""); setResult(null);
    try { const res = await api.get(path, { timeout: 60000 }); setResult(res.data); }
    catch (err) { setError(err.friendlyMessage || "Sandbox check failed"); }
    finally { setBusy(false); }
  };

  const sendSafeTest = async () => {
    if (!confirm("Send one test email to the configured developer/test address only? No real subscriber will receive it.")) return;
    setBusy(true); setError(""); setResult(null);
    try { const res = await api.post("/admin/actions/send-test-email", null, { timeout: 60000 }); setResult({ status: "test_email_sent", ...res.data, safe: true }); }
    catch (err) { setError(err.friendlyMessage || "Test email failed"); }
    finally { setBusy(false); }
  };

  return <div className="admin-page">
    <div className="admin-title">Production Sandbox</div>
    <p style={{ color: "var(--ink-faint)", maxWidth: 720 }}>Run safe readiness checks before deployment. Readiness and scheduler simulation are read-only. The test email is the only action that sends anything, and it uses the configured developer/test address rather than subscribers.</p>
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 18 }}>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/suite")}>{busy ? "Running..." : "Run full sandbox suite"}</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/health")}>System health</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/features")}>Feature readiness</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/automatic-email")}>Simulate automatic email</button>
      <button className="btn-secondary" disabled={busy} onClick={sendSafeTest}>Send safe test email</button>
    </div>
    {busy && <div className="loader" style={{ padding: "30px 0" }}>Running sandbox check...</div>}
    {error && <div className="error-text">{error}</div>}
    {result && <div style={{ marginTop: 24, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 18 }}>
      <div style={{ fontWeight: 700 }}>Result: {result.status || "completed"}</div>
      <SuiteSummary result={result} />
      {result.checks && <CheckList title="Checks" checks={result.checks} />}
      {result.health?.checks && <CheckList title="System health" checks={result.health.checks} />}
      {result.features?.checks && <CheckList title="Feature readiness" checks={result.features.checks} />}
      {result.inspected_users && <SimulationRows users={result.inspected_users} />}
      {result.automatic_email?.inspected_users && <SimulationRows users={result.automatic_email.inspected_users} />}
      {result.detail && <div style={{ marginTop: 10, color: "var(--ink-faint)" }}>{result.detail}</div>}
      <details style={{ marginTop: 18 }}><summary>Raw response</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 10 }}>{JSON.stringify(result, null, 2)}</pre></details>
    </div>}
  </div>;
}
