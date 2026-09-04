import { useEffect, useMemo, useState } from "react";
import api from "../api";
import Loader from "../components/Loader";

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
  ready: "var(--surface)",
  idle: "var(--surface)",
};

function Pill({ status }) {
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 700,
        padding: "5px 10px",
        borderRadius: 14,
        border: "1px solid var(--border)",
        background: bg[status] || "var(--surface)",
      }}
    >
      {labels[status] || status || "Ready"}
    </span>
  );
}

function Step({ title, status, detail, time, last = false }) {
  const dot =
    status === "completed"
      ? "#2e7d4f"
      : status === "failed"
      ? "#c0392b"
      : status === "in_progress"
      ? "#4777b8"
      : status === "scheduled"
      ? "#4777b8"
      : status === "waiting"
      ? "#b8860b"
      : "var(--surface)";

  return (
    <div style={{ display: "flex", gap: 12, minHeight: last ? 48 : 68 }}>
      <div style={{ width: 22, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ width: 16, height: 16, borderRadius: "50%", border: "2px solid var(--border)", background: dot }} />
        {!last && <div style={{ width: 2, flex: 1, background: "var(--border)", marginTop: 3 }} />}
      </div>
      <div style={{ flex: 1, paddingBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
          <strong>{title}</strong>
          <Pill status={status} />
        </div>
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 3 }}>{detail}</div>
        {time && <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>{time}</div>}
      </div>
    </div>
  );
}

function format(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function scheduleLabel(s) {
  if (!s?.enabled) return "Disabled";
  return s.frequency === "once"
    ? `One time · ${s.date || "date"} at ${s.time}`
    : `Daily · ${s.time}`;
}

function effectiveStatus(job, schedule) {
  if (job?.status === "in_progress") return "in_progress";
  if (job?.status === "failed") return "failed";
  if (job?.status === "completed") return "completed";
  if (schedule?.last_status === "failed") return "failed";
  if (schedule?.last_status === "completed") return "completed";
  if (schedule?.enabled) return "waiting";
  return job?.status || schedule?.last_status || "ready";
}

function JobCard({ title, job, schedule, description }) {
  const status = effectiveStatus(job, schedule);
  const done = status === "completed";
  const failed = status === "failed";
  const running = status === "in_progress";
  const waiting = status === "waiting";

  return (
    <div style={{ padding: 20, border: "1px solid var(--border)", borderRadius: 12, marginTop: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontFamily: "var(--serif)", margin: 0 }}>{title}</h3>
          <div style={{ fontSize: 13, color: "var(--ink-faint)", marginTop: 5 }}>{description}</div>
        </div>
        <Pill status={status} />
      </div>

      <div style={{ fontSize: 13, color: "var(--ink-faint)", marginTop: 12 }}>
        Schedule: <strong>{scheduleLabel(schedule)}</strong>{schedule?.timezone ? ` · ${schedule.timezone}` : ""}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink-faint)", marginTop: 3 }}>
        Next run: <strong>{format(schedule?.next_run_at)}</strong>
      </div>
      <div style={{ fontSize: 13, color: "var(--ink-faint)", marginTop: 3 }}>
        Last run: <strong>{format(schedule?.last_run_at || job?.completed_at || job?.started_at)}</strong>
      </div>

      <div style={{ marginTop: 18 }}>
        <Step
          title="Scheduled"
          status={schedule?.enabled || schedule?.last_run_at ? "completed" : "ready"}
          detail={schedule?.enabled ? `Configured for ${scheduleLabel(schedule)}.` : "No active schedule configured."}
        />
        <Step
          title="Waiting"
          status={running || done || failed ? "completed" : schedule?.enabled ? "waiting" : "ready"}
          detail={running ? "The job has been claimed and is running." : done ? "The latest scheduled run completed successfully. Waiting for the next run." : failed ? "The latest scheduled run failed." : waiting ? "Waiting for the next scheduled trigger." : "Waiting for the first scheduled trigger."}
        />
        <Step
          title="In Progress"
          status={running ? "in_progress" : done || failed ? "completed" : "ready"}
          detail={running ? "Work is actively executing now." : done ? "Latest execution finished successfully." : failed ? "Execution stopped with an error." : "Not running yet."}
          time={job?.started_at}
        />
        <Step
          last
          title={failed ? "Failed" : "Completed"}
          status={failed ? "failed" : done ? "completed" : "ready"}
          detail={done ? JSON.stringify(job?.result || schedule?.last_result || {}) : failed ? (job?.error || schedule?.last_result?.error || "Execution failed.") : "Waiting for execution."}
          time={job?.completed_at}
        />
      </div>
    </div>
  );
}

export default function Operations() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  const load = () =>
    api
      .get("/admin/jobs")
      .then((r) => {
        setData(r.data);
        setError("");
      })
      .catch((e) => setError(e.friendlyMessage || "Couldn't load job status"));

  useEffect(() => {
    load().finally(() => setLoading(false));
    const id = setInterval(() => {
      setNow(Date.now());
      load();
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const emailNext = useMemo(() => {
    const t = data?.schedules?.email?.next_run_at ? new Date(data.schedules.email.next_run_at).getTime() : 0;
    return t ? Math.max(0, t - now) : 0;
  }, [data, now]);

  const countdown = emailNext < 60000
    ? `${Math.ceil(emailNext / 1000)} sec`
    : emailNext < 3600000
    ? `${Math.floor(emailNext / 60000)} min ${Math.floor((emailNext % 60000) / 1000)} sec`
    : `${Math.floor(emailNext / 3600000)} hr ${Math.floor((emailNext % 3600000) / 60000)} min`;

  if (loading) return <Loader text="Loading job monitor..." />;

  const schedules = data?.schedules || {};
  const heartbeat = data?.scheduler?.last_tick_at;
  const heartbeatAge = heartbeat ? Math.floor((Date.now() - new Date(heartbeat).getTime()) / 1000) : null;
  const schedulerHealthy = heartbeatAge !== null && heartbeatAge < 30;

  return (
    <div className="admin-page">
      <div className="admin-title">Jobs</div>
      {error && <div className="error-text">{error}</div>}

      <div style={{ padding: 18, border: "1px solid var(--border)", borderRadius: 12, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontWeight: 700 }}>Automatic scheduling</div>
            <div style={{ fontSize: 13, color: "var(--ink-faint)", marginTop: 5 }}>
              Mode: <strong>{schedules.mode || "auto"}</strong> · Timezone: <strong>{schedules.timezone || "Asia/Kolkata"}</strong>
            </div>
          </div>
          <Pill status={schedulerHealthy ? "completed" : "failed"} />
        </div>
        <div style={{ fontSize: 20, fontWeight: 800, marginTop: 10 }}>
          {schedules.email?.enabled ? `Email next run in ${countdown}` : "Email schedule disabled"}
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 6 }}>
          Scheduler heartbeat: {format(heartbeat)}{heartbeatAge !== null ? ` · ${heartbeatAge}s ago` : ""}
        </div>
      </div>

      <JobCard title="News ingestion" job={data?.ingestion?.job || data?.ingestion} schedule={schedules.ingestion} description="Fetch → cluster → generate → verify → approval/publication." />
      <JobCard title="Real-user email delivery" job={data?.email} schedule={schedules.email} description="Select the best eligible approved stories for each active subscriber and deliver them." />
      <JobCard title="Safe test email" job={data?.test_email} schedule={schedules.test_email} description="Developer/test recipient only; never sent to subscribers." />

      <div style={{ marginTop: 18, padding: 14, border: "1px solid var(--border)", borderRadius: 10, fontSize: 12.5, color: "var(--ink-faint)" }}>
        Scheduling is configured only in <strong>Admin → Settings → Scheduling</strong>. This page is the single operational status monitor.
      </div>
    </div>
  );
}
