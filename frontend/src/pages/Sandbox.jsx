import { useEffect, useState } from "react";
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
  return <div style={{ marginTop: 18 }}><h3 style={{ fontFamily: "var(--serif)" }}>Email simulation</h3>{users.map((u) => <div key={u.user_id} style={{ padding: 10, borderBottom: "1px solid var(--border)", fontSize: 13 }}><strong>User #{u.user_id}</strong> · {u.timezone} · configured {u.configured_send_time} · approved: {u.approved_stories} · selected: {u.selected_stories} · <strong>{u.would_send ? "WOULD SEND" : `would not send (${u.decision})`}</strong>{u.selected_headlines?.length > 0 && <div style={{ marginTop: 5, color: "var(--ink-faint)" }}>Selected: {u.selected_headlines.join(" · ")}</div>}</div>)}</div>;
}

export default function Sandbox() {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [simulationDate, setSimulationDate] = useState("");
  const [schedule, setSchedule] = useState(null);
  const [testHour, setTestHour] = useState("12");
  const [testMinute, setTestMinute] = useState("00");

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

  const loadSchedule = async () => {
    try { const res = await api.get("/admin/sandbox/test-email-schedule"); setSchedule(res.data); }
    catch (err) { setError(err.friendlyMessage || "Could not load test schedule"); }
  };

  useEffect(() => { loadSchedule(); }, []);

  const scheduleTest = async () => {
    const hour = Number(testHour); const minute = Number(testMinute);
    if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) { setError("Enter a valid time in 24-hour HH:MM format."); return; }
    if (!confirm(`Schedule a SAFE test email for ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")} (Asia/Kolkata)? It will go only to the configured developer/test address.`)) return;
    setBusy(true); setError("");
    try { const res = await api.post(`/admin/sandbox/test-email-schedule?hour=${hour}&minute=${minute}`, null, { timeout: 30000 }); setSchedule(res.data); }
    catch (err) { setError(err.friendlyMessage || "Could not schedule test email"); }
    finally { setBusy(false); }
  };

  const cancelSchedule = async () => {
    setBusy(true); setError("");
    try { const res = await api.delete("/admin/sandbox/test-email-schedule"); setSchedule(res.data); }
    catch (err) { setError(err.friendlyMessage || "Could not cancel test email"); }
    finally { setBusy(false); }
  };

  const runSimulation = () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(simulationDate)) { setError("Choose an edition date first."); return; }
    run(`/admin/sandbox/simulate?edition_date=${encodeURIComponent(simulationDate)}`);
  };

  return <div className="admin-page">
    <div className="admin-title">Production Sandbox</div>
    <p style={{ color: "var(--ink-faint)", maxWidth: 760 }}>Run safe readiness checks before deployment. Simulations are read-only. Test emails go only to the configured developer/test address and never to subscribers.</p>

    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 18 }}>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/suite")}>{busy ? "Running..." : "Run full sandbox suite"}</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/health")}>System health</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/features")}>Feature readiness</button>
      <button className="btn-secondary" disabled={busy} onClick={() => run("/admin/sandbox/automatic-email")}>Simulate automatic email</button>
      <button className="btn-secondary" disabled={busy} onClick={sendSafeTest}>Send safe test email</button>
    </div>

    <div style={{ marginTop: 28, padding: 18, border: "1px solid var(--border)", borderRadius: 10 }}>
      <h3 style={{ fontFamily: "var(--serif)", marginTop: 0 }}>Test an existing approved edition</h3>
      <p style={{ color: "var(--ink-faint)", fontSize: 13 }}>Pick a date such as 2026-08-31 to verify that the same personalization logic selects the best configured number of stories. Nothing is sent.</p>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input type="date" value={simulationDate} onChange={(e) => setSimulationDate(e.target.value)} />
        <button className="btn-secondary" disabled={busy} onClick={runSimulation}>Simulate this edition</button>
      </div>
    </div>

    <div style={{ marginTop: 28, padding: 18, border: "1px solid var(--border)", borderRadius: 10 }}>
      <h3 style={{ fontFamily: "var(--serif)", marginTop: 0 }}>Schedule a safe automatic test email</h3>
      <p style={{ color: "var(--ink-faint)", fontSize: 13 }}>Enter <strong>hour and minute in 24-hour format</strong>. Example: 11:55. The system sends exactly one test email to the configured developer/test address when GitHub Actions next checks after that time.</p>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input aria-label="Test email hour" type="number" min="0" max="23" value={testHour} onChange={(e) => setTestHour(e.target.value)} style={{ width: 70 }} />
        <span>:</span>
        <input aria-label="Test email minute" type="number" min="0" max="59" value={testMinute} onChange={(e) => setTestMinute(e.target.value)} style={{ width: 70 }} />
        <button className="btn-secondary" disabled={busy} onClick={scheduleTest}>Schedule test email</button>
        {schedule?.enabled && <button className="btn-secondary" disabled={busy} onClick={cancelSchedule}>Cancel</button>}
      </div>
      {schedule?.enabled && <div style={{ marginTop: 10, fontSize: 13 }}><strong>Scheduled:</strong> {schedule.scheduled_at} · one-shot · safe</div>}
      {schedule?.last_result && <div style={{ marginTop: 8, color: "var(--ink-faint)", fontSize: 13 }}><strong>Last result:</strong> {schedule.last_result}</div>}
      {!schedule?.recipient_configured && <div style={{ marginTop: 8, color: "var(--ink-faint)", fontSize: 13 }}>Configure <code>developer_test_email</code> in Admin → Settings first.</div>}
    </div>

    {busy && <div className="loader" style={{ padding: "30px 0" }}>Running sandbox check...</div>}
    {error && <div className="error-text">{error}</div>}
    {result && <div style={{ marginTop: 24, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 18 }}>
      <div style={{ fontWeight: 700 }}>Result: {result.status || "completed"}</div>
      <SuiteSummary result={result} />
      {result.checks && <CheckList title="Checks" checks={result.checks} />}
      {result.health?.checks && <CheckList title="System health" checks={result.health.checks} />}
      {result.features?.checks && <CheckList title="Feature readiness" checks={result.features.checks} />}
      {result.users && <SimulationRows users={result.users} />}
      {result.inspected_users && <SimulationRows users={result.inspected_users} />}
      {result.automatic_email?.inspected_users && <SimulationRows users={result.automatic_email.inspected_users} />}
      {result.detail && <div style={{ marginTop: 10, color: "var(--ink-faint)" }}>{result.detail}</div>}
      <details style={{ marginTop: 18 }}><summary>Raw response</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 10 }}>{JSON.stringify(result, null, 2)}</pre></details>
    </div>}
  </div>;
}
