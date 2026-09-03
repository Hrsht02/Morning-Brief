import { useCallback, useEffect, useState } from "react";
import api from "../../api";

const emptySchedule = { enabled: false, frequency: "daily", date: "", time: "06:00", timezone: "Asia/Kolkata", next_run_at: null, last_run_at: null, last_status: "ready", last_result: null, freshness_mode: "since_last_successful", freshness_after: null };

function localInputFromIso(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatRun(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function ScheduleCard({ type, value, setValue, onSave, onCancel, saving }) {
  const ingestion = type === "ingestion";
  const schedule = value || emptySchedule;
  const set = (key, next) => setValue({ ...schedule, [key]: next });
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 12, padding: 18, marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontFamily: "var(--serif)", margin: 0 }}>{ingestion ? "News ingestion" : "Real-user email delivery"}</h3>
          <p style={{ color: "var(--ink-faint)", fontSize: 13, margin: "5px 0 0" }}>
            {ingestion ? "Automatically fetch and process new news." : "Automatically send the current approved content to eligible subscribers."}
          </p>
        </div>
        <span style={{ fontSize: 12, fontWeight: 700, padding: "5px 10px", borderRadius: 14, background: schedule.enabled ? "#eef7f0" : "var(--surface)", border: "1px solid var(--border)" }}>{schedule.enabled ? "Enabled" : "Disabled"}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginTop: 18 }}>
        <label style={{ fontSize: 13 }}>
          Frequency
          <select value={schedule.frequency} onChange={(e) => set("frequency", e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
            <option value="daily">Daily</option>
            <option value="once">One time</option>
          </select>
        </label>
        {schedule.frequency === "once" && (
          <label style={{ fontSize: 13 }}>
            Date
            <input type="date" value={schedule.date || ""} onChange={(e) => set("date", e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
          </label>
        )}
        <label style={{ fontSize: 13 }}>
          Time
          <input type="time" value={schedule.time || "06:00"} onChange={(e) => set("time", e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
        </label>
      </div>

      {ingestion && (
        <div style={{ marginTop: 18, padding: 14, background: "var(--surface)", borderRadius: 10 }}>
          <strong style={{ fontSize: 13 }}>Only ingest news after</strong>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 10, fontSize: 13 }}>
            <label><input type="radio" name="freshness-mode" checked={(schedule.freshness_mode || "since_last_successful") === "since_last_successful"} onChange={() => set("freshness_mode", "since_last_successful")} /> Since last successful ingestion</label>
            <label><input type="radio" name="freshness-mode" checked={schedule.freshness_mode === "after_datetime"} onChange={() => set("freshness_mode", "after_datetime")} /> After a specific date &amp; time</label>
          </div>
          {schedule.freshness_mode === "after_datetime" && (
            <input type="datetime-local" value={localInputFromIso(schedule.freshness_after)} onChange={(e) => set("freshness_after", e.target.value)} style={{ marginTop: 10 }} />
          )}
          <div style={{ color: "var(--ink-faint)", fontSize: 12, marginTop: 8 }}>
            {schedule.freshness_mode === "after_datetime" ? "Articles at or before this timestamp are ignored." : "The system advances the checkpoint only after a successful ingestion."}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 9, flexWrap: "wrap", alignItems: "center", marginTop: 16 }}>
        <button className="btn-secondary" disabled={saving} onClick={onSave}>{saving ? "Saving…" : "Save schedule"}</button>
        {schedule.enabled && <button className="btn-secondary" disabled={saving} onClick={onCancel}>Disable schedule</button>}
      </div>
      <div style={{ color: "var(--ink-faint)", fontSize: 12, marginTop: 12 }}>
        Timezone: <strong>{schedule.timezone || "Asia/Kolkata"}</strong> · Next run: <strong>{formatRun(schedule.next_run_at)}</strong>
      </div>
    </div>
  );
}

export default function SchedulingSettings({ showToast }) {
  const [data, setData] = useState(null);
  const [email, setEmail] = useState(emptySchedule);
  const [ingestion, setIngestion] = useState(emptySchedule);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api.get("/admin/schedules", { timeout: 15000 });
      setData(res.data);
      setEmail({ ...emptySchedule, ...(res.data?.email || {}) });
      setIngestion({ ...emptySchedule, ...(res.data?.ingestion || {}) });
      setError("");
    } catch (err) { setError(err.friendlyMessage || "Could not load schedules"); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (type, value) => {
    setSaving(type); setError("");
    try {
      const payload = { frequency: value.frequency, date: value.frequency === "once" ? value.date : null, time: value.time };
      if (type === "ingestion") {
        payload.freshness_mode = value.freshness_mode || "since_last_successful";
        payload.freshness_after = payload.freshness_mode === "after_datetime" ? value.freshness_after : null;
      }
      const res = await api.put(`/admin/schedules/${type}`, payload, { timeout: 15000 });
      if (type === "email") setEmail(res.data); else setIngestion(res.data);
      showToast(`${type === "email" ? "Email" : "Ingestion"} schedule saved`);
    } catch (err) { setError(err.friendlyMessage || `Could not save ${type} schedule`); }
    finally { setSaving(""); }
  };

  const disable = async (type) => {
    setSaving(type); setError("");
    try {
      const res = await api.delete(`/admin/schedules/${type}`, { timeout: 15000 });
      if (type === "email") setEmail(res.data); else setIngestion(res.data);
      showToast(`${type === "email" ? "Email" : "Ingestion"} schedule disabled`);
    } catch (err) { setError(err.friendlyMessage || "Could not disable schedule"); }
    finally { setSaving(""); }
  };

  if (!data) return <div style={{ padding: 20, color: "var(--ink-faint)" }}>Loading schedules…</div>;
  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontFamily: "var(--serif)", marginBottom: 4 }}>Scheduling</h2>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, maxWidth: 760 }}>
        One place for production schedules. Choose a one-time date or a daily time. The configured timezone is used for both jobs, and the scheduler is shared by the Render runtime and recovery cron.
      </p>
      {error && <div className="error-text" style={{ marginTop: 10 }}>{error}</div>}
      <ScheduleCard type="email" value={email} setValue={setEmail} onSave={() => save("email", email)} onCancel={() => disable("email")} saving={saving === "email"} />
      <ScheduleCard type="ingestion" value={ingestion} setValue={setIngestion} onSave={() => save("ingestion", ingestion)} onCancel={() => disable("ingestion")} saving={saving === "ingestion"} />
    </div>
  );
}
