import { useCallback, useEffect, useRef, useState } from "react";
import api from "../../api";

const empty = {
  enabled: false,
  frequency: "daily",
  date: "",
  time: "06:00",
  timezone: "Asia/Kolkata",
  next_run_at: null,
  last_run_at: null,
  last_status: "ready",
  last_result: null,
  freshness_mode: "since_last_successful",
  freshness_after: null,
};

const labels = {
  ready: "Ready",
  scheduled: "Scheduled",
  waiting: "Waiting",
  in_progress: "In Progress",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  idle: "Ready",
};

const bg = {
  completed: "#eef7f0",
  failed: "#fff0ed",
  in_progress: "#eef4ff",
  scheduled: "#eef4ff",
  waiting: "#fff8df",
  cancelled: "#f3f3f3",
};

function format(v) {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString();
}

function Status({ status }) {
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 700,
        padding: "5px 9px",
        borderRadius: 14,
        border: "1px solid var(--border)",
        background: bg[status] || "var(--surface)",
      }}
    >
      {labels[status] || status || "Ready"}
    </span>
  );
}

function Tracker({ type, data }) {
  const job = data?.[type]?.job || data?.[type] || {};
  const schedule = data?.schedules?.[type] || {};
  const status = job.status || schedule.last_status || "ready";
  const result = job.result ?? schedule.last_result;
  const progress = type === "ingestion" ? data?.ingestion?.progress : null;

  return (
    <div style={{ marginTop: 14, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 12 }}>Latest run</strong>
        <Status status={status} />
      </div>

      {type === "ingestion" && progress?.total_clusters > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 700, marginTop: 10 }}>
            Progress: {Math.min(progress.current_cluster, progress.total_clusters)}/{progress.total_clusters} clusters
          </div>
          <div style={{ height: 7, background: "var(--surface-2)", borderRadius: 8, overflow: "hidden", marginTop: 6 }}>
            <div
              style={{
                height: "100%",
                width: `${Math.min(100, (progress.current_cluster / progress.total_clusters) * 100)}%`,
                background: "var(--accent)",
                transition: "width .3s",
              }}
            />
          </div>
          <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 5 }}>
            {progress.stage || "Working"}
            {progress.cancel_requested ? " · Stop requested; finishing current API call…" : ""}
          </div>
        </>
      )}

      <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 6 }}>
        Started: {format(job.started_at || schedule.last_run_at)} · Finished: {format(job.completed_at)}
      </div>
      {job.error && <div style={{ fontSize: 12, color: "#b8442f", marginTop: 6 }}>{job.error}</div>}
      {result && (
        <details style={{ marginTop: 7 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 700 }}>View details</summary>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 11, marginTop: 8, maxHeight: 220, overflow: "auto" }}>
            {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function ScheduleCard({
  type,
  value,
  setValue,
  onEdit,
  onSave,
  onCancel,
  saving,
  data,
  emailTopN,
  setEmailTopN,
  onEditStorage,
  onRunNow,
  onStop,
}) {
  const ingestion = type === "ingestion";
  const s = value || empty;
  const set = (key, value) => {
    setValue({ ...s, [key]: value });
    onEdit?.();
  };
  const running = data?.ingestion?.job?.status === "in_progress";
  const stopping = data?.ingestion?.progress?.cancel_requested;

  return (
    <section style={{ border: "1px solid var(--border)", borderRadius: 14, padding: 18, background: "var(--surface)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
        <div>
          <h3 style={{ fontFamily: "var(--serif)", margin: 0 }}>{ingestion ? "News ingestion" : "Email delivery"}</h3>
          <p style={{ color: "var(--ink-faint)", fontSize: 12.5, margin: "5px 0 0" }}>
            {ingestion ? "Fetch, process and approve new stories automatically." : "Send personalized approved stories to eligible subscribers."}
          </p>
        </div>
        <Status status={s.enabled ? "scheduled" : "ready"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10, marginTop: 16 }}>
        <label style={{ fontSize: 12.5 }}>
          Frequency
          <select value={s.frequency} onChange={(e) => set("frequency", e.target.value)} style={{ display: "block", width: "100%", marginTop: 5 }}>
            <option value="daily">Daily</option>
            <option value="once">One time</option>
          </select>
        </label>

        {s.frequency === "once" && (
          <label style={{ fontSize: 12.5 }}>
            Date
            <input type="date" value={s.date || ""} onChange={(e) => set("date", e.target.value)} style={{ display: "block", width: "100%", marginTop: 5 }} />
          </label>
        )}

        <label style={{ fontSize: 12.5 }}>
          Time (24-hour)
          <input type="time" value={s.time || "00:00"} onChange={(e) => set("time", e.target.value)} style={{ display: "block", width: "100%", marginTop: 5 }} />
        </label>

        {!ingestion && (
          <label style={{ fontSize: 12.5 }}>
            Email Top N
            <input
              type="number"
              min="1"
              max="200"
              value={emailTopN}
              onChange={(e) => {
                setEmailTopN(e.target.value);
                onEditStorage?.();
              }}
              style={{ display: "block", width: "100%", marginTop: 5 }}
            />
          </label>
        )}
      </div>

      {ingestion && (
        <>
          <div style={{ marginTop: 14, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
            <strong style={{ fontSize: 12.5 }}>Ingestion freshness</strong>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 9, fontSize: 12.5 }}>
              <label>
                <input
                  type="radio"
                  name="freshness-mode"
                  checked={(s.freshness_mode || "since_last_successful") === "since_last_successful"}
                  onChange={() => set("freshness_mode", "since_last_successful")}
                />{" "}
                Since last successful ingestion
              </label>
              <label>
                <input
                  type="radio"
                  name="freshness-mode"
                  checked={s.freshness_mode === "after_datetime"}
                  onChange={() => set("freshness_mode", "after_datetime")}
                />{" "}
                After specific date/time
              </label>
            </div>
            {s.freshness_mode === "after_datetime" && (
              <input
                type="datetime-local"
                value={s.freshness_after ? s.freshness_after.slice(0, 16) : ""}
                onChange={(e) => set("freshness_after", e.target.value)}
                style={{ marginTop: 9 }}
              />
            )}
            <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 7 }}>
              {s.freshness_mode === "after_datetime"
                ? "Only articles newer than this timestamp are considered."
                : "The checkpoint advances only after a successful ingestion, preventing gaps after failures."}
            </div>
          </div>

          <div style={{ marginTop: 14, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
            <strong style={{ fontSize: 12.5 }}>Ingestion options</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10, marginTop: 9 }}>
              <label style={{ fontSize: 12 }}>
                Max clusters per run
                <input
                  type="number"
                  min="1"
                  max="200"
                  value={data?.ingestion_options?.max_clusters_per_run ?? 100}
                  onChange={(e) => data.setMaxClusters?.(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 5 }}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                Pause between clusters (sec)
                <input
                  type="number"
                  min="0"
                  max="60"
                  step="0.5"
                  value={data?.ingestion_options?.llm_pause_seconds ?? 1}
                  onChange={(e) => data.setLlmPause?.(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 5 }}
                />
              </label>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 7 }}>
              Lower values are faster, but provider rate limits still apply. The run remains cancellable.
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <button className="btn-secondary" disabled={saving || running} onClick={onRunNow}>
                {running ? "Ingestion running…" : "Run ingestion now"}
              </button>
              {running && (
                <button className="btn-secondary" disabled={stopping} onClick={onStop}>
                  {stopping ? "Stop requested…" : "Stop ingestion"}
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {!ingestion && (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 10 }}>
          Personalization is applied before Top N. A user who selects FinTech receives only matching stories; an empty selection means all news.
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        <button className="btn-secondary" disabled={saving} onClick={onSave}>{saving ? "Saving…" : "Save schedule"}</button>
        {s.enabled && <button className="btn-secondary" disabled={saving} onClick={onCancel}>Disable</button>}
      </div>

      <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 10 }}>
        Timezone: <strong>{s.timezone || "Asia/Kolkata"}</strong> · Next: <strong>{format(s.next_run_at)}</strong>
      </div>

      <Tracker type={type} data={data} />
    </section>
  );
}

export default function SchedulingSettings({ showToast }) {
  const [data, setData] = useState(null);
  const [email, setEmail] = useState(empty);
  const [ingestion, setIngestion] = useState(empty);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [emailTopN, setEmailTopN] = useState(25);
  const [retentionDays, setRetentionDays] = useState(7);
  const [maxClusters, setMaxClusters] = useState(100);
  const [llmPause, setLlmPause] = useState(1);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const dirtyRef = useRef({ email: false, ingestion: false, storage: false });

  const load = useCallback(async () => {
    try {
      const [res, jobs, settings] = await Promise.all([
        api.get("/admin/schedules", { timeout: 15000 }),
        api.get("/admin/jobs", { timeout: 15000 }),
        api.get("/admin/settings", { timeout: 15000 }),
      ]);

      const map = Object.fromEntries((settings.data || []).map((s) => [s.key, s.value]));
      setData({
        ...res.data,
        ...jobs.data,
        ingestion_options: {
          max_clusters_per_run: Number(map.max_clusters_per_run || 100),
          llm_pause_seconds: Number(map.llm_pause_seconds || 1),
        },
      });

      // The status/dashboard data is refreshed every 5 seconds, but an active form
      // must never be overwritten by that background refresh. This was the cause
      // of date/time values jumping back to the previous schedule while editing.
      if (!dirtyRef.current.email) {
        setEmail({ ...empty, ...(res.data?.email || {}) });
      }
      if (!dirtyRef.current.ingestion) {
        setIngestion({ ...empty, ...(res.data?.ingestion || {}) });
      }
      if (!dirtyRef.current.storage) {
        setEmailTopN(Number(map.email_top_n || 25));
        setRetentionDays(Number(map.news_retention_days || 7));
        setMaxClusters(Number(map.max_clusters_per_run || 100));
        setLlmPause(Number(map.llm_pause_seconds || 1));
      }
      setError("");
    } catch (err) {
      setError(err.friendlyMessage || "Could not load schedules");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const save = async (type, value) => {
    setSaving(type);
    setError("");
    try {
      const payload = {
        frequency: value.frequency,
        date: value.frequency === "once" ? value.date : null,
        time: value.time,
      };
      if (type === "ingestion") {
        payload.freshness_mode = value.freshness_mode || "since_last_successful";
        payload.freshness_after = payload.freshness_mode === "after_datetime" ? value.freshness_after : null;
      }

      const res = await api.put(`/admin/schedules/${type}`, payload, { timeout: 15000 });
      dirtyRef.current[type] = false;
      if (type === "email") setEmail(res.data);
      else setIngestion(res.data);
      showToast(`${type === "email" ? "Email" : "Ingestion"} schedule saved`);
      await load();
    } catch (err) {
      setError(err.friendlyMessage || `Could not save ${type} schedule`);
    } finally {
      setSaving("");
    }
  };

  const disable = async (type) => {
    setSaving(type);
    setError("");
    try {
      const res = await api.delete(`/admin/schedules/${type}`, { timeout: 15000 });
      dirtyRef.current[type] = false;
      if (type === "email") setEmail(res.data);
      else setIngestion(res.data);
      showToast(`${type === "email" ? "Email" : "Ingestion"} schedule disabled`);
      await load();
    } catch (err) {
      setError(err.friendlyMessage || "Could not disable schedule");
    } finally {
      setSaving("");
    }
  };

  const saveStorage = async () => {
    setSettingsSaving(true);
    setError("");
    try {
      await api.put("/admin/settings/email_top_n", { value: String(Math.max(1, Math.min(200, Number(emailTopN) || 25))) }, { timeout: 15000 });
      await api.put("/admin/settings/news_retention_days", { value: String(Math.max(1, Math.min(365, Number(retentionDays) || 7))) }, { timeout: 15000 });
      await api.put("/admin/settings/max_clusters_per_run", { value: String(Math.max(1, Math.min(200, Number(maxClusters) || 100))) }, { timeout: 15000 });
      await api.put("/admin/settings/llm_pause_seconds", { value: String(Math.max(0, Math.min(60, Number(llmPause) || 0))) }, { timeout: 15000 });
      dirtyRef.current.storage = false;
      showToast("Ingestion and delivery settings saved");
      await load();
    } catch (err) {
      setError(err.friendlyMessage || "Could not save settings");
    } finally {
      setSettingsSaving(false);
    }
  };

  const runNow = async () => {
    setError("");
    try {
      await api.post("/admin/actions/run-ingestion", {}, { timeout: 15000 });
      showToast("Ingestion started");
      await load();
    } catch (err) {
      setError(err.friendlyMessage || "Could not start ingestion");
    }
  };

  const stopNow = async () => {
    setError("");
    try {
      await api.put("/admin/settings/ingestion_cancel_requested", { value: "true" }, { timeout: 15000 });
      showToast("Stop requested; current API call will finish safely");
      await load();
    } catch (err) {
      setError(err.friendlyMessage || "Could not request ingestion stop");
    }
  };

  const optionData = {
    ...data,
    ingestion_options: { max_clusters_per_run: maxClusters, llm_pause_seconds: llmPause },
    setMaxClusters: (value) => {
      dirtyRef.current.storage = true;
      setMaxClusters(value);
    },
    setLlmPause: (value) => {
      dirtyRef.current.storage = true;
      setLlmPause(value);
    },
  };

  if (!data) return <div style={{ padding: 18, color: "var(--ink-faint)" }}>Loading schedules…</div>;

  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontFamily: "var(--serif)", marginBottom: 4 }}>Scheduling</h2>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, maxWidth: 820 }}>
        One control area for production timing, ingestion controls, freshness, email volume and storage retention. Jobs are tracked inline beside each schedule.
      </p>
      {error && <div className="error-text" style={{ marginTop: 10 }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 16, marginTop: 14 }}>
        <ScheduleCard
          type="ingestion"
          value={ingestion}
          setValue={setIngestion}
          onEdit={() => { dirtyRef.current.ingestion = true; }}
          onSave={() => save("ingestion", ingestion)}
          onCancel={() => disable("ingestion")}
          saving={saving === "ingestion"}
          data={optionData}
          onRunNow={runNow}
          onStop={stopNow}
        />
        <ScheduleCard
          type="email"
          value={email}
          setValue={setEmail}
          onEdit={() => { dirtyRef.current.email = true; }}
          onSave={() => save("email", email)}
          onCancel={() => disable("email")}
          saving={saving === "email"}
          data={data}
          emailTopN={emailTopN}
          setEmailTopN={setEmailTopN}
          onEditStorage={() => { dirtyRef.current.storage = true; }}
        />
      </div>

      <section style={{ marginTop: 16, border: "1px solid var(--border)", borderRadius: 14, padding: 18, background: "var(--surface)" }}>
        <h3 style={{ fontFamily: "var(--serif)", margin: 0 }}>Database retention & ingestion controls</h3>
        <p style={{ fontSize: 12.5, color: "var(--ink-faint)", margin: "5px 0 14px" }}>
          Keep the free database small and tune ingestion workload. Saving these values affects future runs; it does not kill a currently running API request.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 10, alignItems: "end" }}>
          <label style={{ fontSize: 12.5 }}>
            Keep news for (days)
            <input type="number" min="1" max="365" value={retentionDays} onChange={(e) => { dirtyRef.current.storage = true; setRetentionDays(e.target.value); }} style={{ display: "block", width: "100%", marginTop: 5 }} />
          </label>
          <label style={{ fontSize: 12.5 }}>
            Max clusters per run
            <input type="number" min="1" max="200" value={maxClusters} onChange={(e) => { dirtyRef.current.storage = true; setMaxClusters(e.target.value); }} style={{ display: "block", width: "100%", marginTop: 5 }} />
          </label>
          <label style={{ fontSize: 12.5 }}>
            Pause between clusters (sec)
            <input type="number" min="0" max="60" step="0.5" value={llmPause} onChange={(e) => { dirtyRef.current.storage = true; setLlmPause(e.target.value); }} style={{ display: "block", width: "100%", marginTop: 5 }} />
          </label>
          <button className="btn-secondary" disabled={settingsSaving} onClick={saveStorage}>{settingsSaving ? "Saving…" : "Save controls"}</button>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 9 }}>
          For the current free-tier setup, start around 25–40 clusters and 0–1 second pause. Provider limits can still make a large run take time.
        </div>
      </section>

      <div style={{ marginTop: 16, padding: 13, border: "1px solid var(--border)", borderRadius: 10, fontSize: 12, color: "var(--ink-faint)" }}>
        <strong>Recommended:</strong> Ingestion <strong>00:00</strong> → Email <strong>05:00</strong> · Freshness <strong>Since last successful ingestion</strong>. The ingestion can now be stopped safely from this page while it is running.
      </div>
    </div>
  );
}
