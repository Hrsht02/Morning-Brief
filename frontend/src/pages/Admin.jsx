import { useEffect, useState, useCallback } from "react";
import api from "../api";
import Loader from "../components/Loader";

const TABS = ["Overview", "Sources", "Verification", "Settings", "Pending Approval", "Developers & API Keys", "Audit Log", "Users"];

export default function Admin() {
  const [tab, setTab] = useState("Overview");
  const [toast, setToast] = useState("");

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3500);
  };

  return (
    <div className="admin-page">
      <div className="admin-title">Admin</div>
      <div className="admin-tabs">
        {TABS.map((t) => (
          <button key={t} className={`admin-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
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

// ---------------- Overview ----------------
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

  // Ingestion is deliberately paced (a few seconds between each AI summary call,
  // to stay within the free LLM tier's rate limits) so a full run can take a
  // few minutes. Rather than holding one long HTTP request open, we start it
  // in the background and poll for completion instead.
  const pollIngestionStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/admin/actions/ingestion-status");
        setIngestionStatus(res.data.status);
        if (res.data.status !== "running") {
          clearInterval(interval);
          setBusy(false);
          if (res.data.status === "error") {
            showToast(`Ingestion failed: ${res.data.last_result?.detail || "unknown error"}`);
          } else {
            const created = res.data.last_result?.stories_created ?? 0;
            showToast(`Ingestion done: ${created} stories created`);
          }
          load();
        }
      } catch {
        clearInterval(interval);
        setBusy(false);
      }
    }, 4000);
  }, [load, showToast]);

  const runIngestion = async () => {
    setBusy(true);
    setIngestionStatus("running");
    try {
      await api.post("/admin/actions/run-ingestion");
      showToast("Ingestion started - this can take a few minutes, feel free to switch tabs and come back");
      pollIngestionStatus();
    } catch (err) {
      setBusy(false);
      showToast(err.friendlyMessage || "Couldn't start ingestion");
    }
  };

  const sendEmailsNow = async () => {
    setBusy(true);
    try {
      const res = await api.post("/admin/actions/send-emails-now", null, { timeout: 6 * 60 * 1000 });
      showToast(`Emails: ${res.data.sent ?? 0} sent, ${res.data.failed ?? 0} failed`);
      load();
    } catch (err) {
      showToast(err.friendlyMessage || "Sending failed");
    } finally {
      setBusy(false);
    }
  };

  const sendTestEmail = async () => {
    setBusy(true);
    try {
      const res = await api.post("/admin/actions/send-test-email", null, { timeout: 60000 });
      showToast(res.data.detail || "Test email sent");
    } catch (err) {
      showToast(err.friendlyMessage || "Test send failed");
    } finally {
      setBusy(false);
    }
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
        <Stat label="Approved today" value={stats.approved_today} />
        <Stat label="Active sources" value={stats.active_sources} />
        <Stat label="High-risk sources" value={stats.high_risk_sources} />
        <Stat label="Sources w/ errors" value={stats.sources_with_errors} />
        <Stat label="Emails sent today" value={stats.emails_sent_today} />
        <Stat label="Developer accounts" value={stats.developer_accounts} />
        <Stat label="Active API keys" value={stats.active_api_keys} />
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button className="btn-secondary" onClick={runIngestion} disabled={busy}>
          {ingestionStatus === "running" ? "Ingesting... (this can take a few minutes)" : "Run ingestion now"}
        </button>
        <button className="btn-secondary" onClick={sendEmailsNow} disabled={busy}>
          {busy ? "Working..." : "Send today's emails now (real users)"}
        </button>
        <button className="btn-secondary" onClick={sendTestEmail} disabled={busy}>
          {busy ? "Working..." : "Send TEST email (safe, to test address only)"}
        </button>
      </div>
    </div>
  );
}

function ModeBadge({ label, value, tone }) {
  const colors = { ok: "#2e7d4f", warn: "#b8442f", danger: "#c0392b" };
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6, background: "#fff", border: "1px solid var(--border)",
      borderRadius: 20, padding: "6px 14px", fontSize: 12.5,
    }}>
      <span style={{ color: "var(--ink-faint)" }}>{label}:</span>
      <span style={{ fontWeight: 700, color: colors[tone] || "#333" }}>{value}</span>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

// ---------------- Sources ----------------
function Sources({ showToast }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", rss_url: "", default_category: "", trust_tier: 2, legal_risk_level: "standard" });

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/sources").then((res) => setSources(res.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const addSource = async (e) => {
    e.preventDefault();
    if (!form.name || !form.rss_url) return;
    try {
      await api.post("/admin/sources", { ...form, trust_tier: Number(form.trust_tier) });
      setForm({ name: "", rss_url: "", default_category: "", trust_tier: 2, legal_risk_level: "standard" });
      showToast("Source added");
      load();
    } catch (err) {
      showToast(err.friendlyMessage || "Couldn't add source");
    }
  };

  const toggleActive = async (source) => {
    try {
      await api.put(`/admin/sources/${source.id}`, { is_active: !source.is_active });
      load();
    } catch (err) {
      showToast(err.friendlyMessage);
    }
  };

  const setRiskLevel = async (source, level) => {
    try {
      await api.put(`/admin/sources/${source.id}`, { legal_risk_level: level });
      showToast(`${source.name} marked as ${level.replace("_", " ")}`);
      load();
    } catch (err) {
      showToast(err.friendlyMessage);
    }
  };

  const deleteSource = async (id) => {
    if (!confirm("Delete this source?")) return;
    try {
      await api.delete(`/admin/sources/${id}`);
      showToast("Source deleted");
      load();
    } catch (err) {
      showToast(err.friendlyMessage);
    }
  };

  if (loading) return <Loader text="Loading sources..." />;

  return (
    <div>
      <form onSubmit={addSource} className="admin-form-row">
        <input placeholder="Source name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="RSS URL" value={form.rss_url} onChange={(e) => setForm({ ...form, rss_url: e.target.value })} />
        <input placeholder="Default category slug" value={form.default_category} onChange={(e) => setForm({ ...form, default_category: e.target.value })} />
        <select value={form.trust_tier} onChange={(e) => setForm({ ...form, trust_tier: e.target.value })}>
          <option value={1}>Tier 1 (wire service)</option>
          <option value={2}>Tier 2 (major outlet)</option>
          <option value={3}>Tier 3 (niche)</option>
        </select>
        <select value={form.legal_risk_level} onChange={(e) => setForm({ ...form, legal_risk_level: e.target.value })}>
          <option value="standard">Standard risk</option>
          <option value="high_risk">High risk (always needs review)</option>
          <option value="blocked">Blocked (never fetched)</option>
        </select>
        <button className="btn-secondary" type="submit">Add source</button>
      </form>

      <table className="admin-table">
        <thead>
          <tr><th>Name</th><th>RSS URL</th><th>Tier</th><th>Legal risk</th><th>Status</th><th>Last fetch</th><th></th></tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.rss_url}</td>
              <td>{s.trust_tier}</td>
              <td>
                <select value={s.legal_risk_level} onChange={(e) => setRiskLevel(s, e.target.value)} style={{ fontSize: 12, padding: "2px 4px" }}>
                  <option value="standard">Standard</option>
                  <option value="high_risk">High risk</option>
                  <option value="blocked">Blocked</option>
                </select>
              </td>
              <td>
                {s.last_fetch_error
                  ? <span className="tag-error" title={s.last_fetch_error}>Error</span>
                  : <span className="tag-ok">OK</span>}
              </td>
              <td>{s.last_fetched_at ? new Date(s.last_fetched_at).toLocaleString() : "Never"}</td>
              <td style={{ display: "flex", gap: 6 }}>
                <button className="icon-btn" onClick={() => toggleActive(s)}>
                  {s.is_active ? "Pause" : "Activate"}
                </button>
                <button className="icon-btn danger" onClick={() => deleteSource(s.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------- Verification Layers ----------------
function VerificationLayers({ showToast }) {
  const [layers, setLayers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/verification-layers").then((res) => setLayers(res.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = async (layer, changes) => {
    try {
      await api.put(`/admin/verification-layers/${layer.id}`, changes);
      showToast(`${layer.name} updated`);
      load();
    } catch (err) {
      showToast(err.friendlyMessage);
    }
  };

  const move = (layer, direction) => {
    const newOrder = layer.sort_order + (direction === "up" ? -1.5 : 1.5);
    update(layer, { sort_order: newOrder });
  };

  if (loading) return <Loader text="Loading verification pipeline..." />;

  return (
    <div>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, marginBottom: 16 }}>
        This is the exact sequence every story passes through before publication. Disable a layer to skip it entirely,
        or mark it advisory-only (non-blocking) so it still flags issues without holding the story for review.
        Reorder with the arrows - order matters for how flags are recorded, though every enabled layer always runs.
      </p>
      <table className="admin-table">
        <thead><tr><th>Order</th><th>Layer</th><th>Enabled</th><th>Blocking</th><th></th></tr></thead>
        <tbody>
          {layers.map((l, i) => (
            <tr key={l.id}>
              <td>
                <button className="icon-btn" onClick={() => move(l, "up")} disabled={i === 0} style={{ marginRight: 4 }}>↑</button>
                <button className="icon-btn" onClick={() => move(l, "down")} disabled={i === layers.length - 1}>↓</button>
              </td>
              <td><strong>{l.name}</strong><br /><code style={{ fontSize: 11, color: "var(--ink-faint)" }}>{l.key}</code></td>
              <td>
                <input type="checkbox" checked={l.is_enabled} onChange={(e) => update(l, { is_enabled: e.target.checked })} />
              </td>
              <td>
                <select value={l.is_blocking ? "blocking" : "advisory"} onChange={(e) => update(l, { is_blocking: e.target.value === "blocking" })} disabled={!l.is_enabled}>
                  <option value="blocking">Blocking (holds for review)</option>
                  <option value="advisory">Advisory only</option>
                </select>
              </td>
              <td></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------- Settings ----------------
function SettingsTab({ showToast }) {
  const [settings, setSettings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState({});

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/settings").then((res) => setSettings(res.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (key) => {
    const value = edits[key];
    if (value === undefined) return;
    try {
      await api.put(`/admin/settings/${key}`, { value });
      showToast(`Updated ${key}`);
      load();
    } catch (err) {
      showToast(err.friendlyMessage);
    }
  };

  if (loading) return <Loader text="Loading settings..." />;

  return (
    <table className="admin-table">
      <thead><tr><th>Key</th><th>Description</th><th>Value</th><th></th></tr></thead>
      <tbody>
        {settings.map((s) => (
          <tr key={s.key}>
            <td><code>{s.key}</code></td>
            <td style={{ color: "var(--ink-faint)", maxWidth: 320 }}>{s.description}</td>
            <td>
              <input
                style={{ width: 140 }}
                defaultValue={s.value}
                onChange={(e) => setEdits({ ...edits, [s.key]: e.target.value })}
              />
            </td>
            <td><button className="icon-btn" onClick={() => save(s.key)}>Save</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------- Pending Approval ----------------
const FLAG_LABELS = {
  low_confidence: { label: "Low AI confidence", color: "#b8442f" },
  near_verbatim_risk: { label: "Too close to original wording", color: "#c0392b" },
  high_risk_source: { label: "High-risk source", color: "#c0392b" },
  blocked_source: { label: "Blocked source", color: "#c0392b" },
  no_citations: { label: "No citations found", color: "#b8442f" },
  verifier_unavailable: { label: "Independent verifier unavailable", color: "#8a6d00" },
  unsupported_claims: { label: "Unsupported claims found", color: "#c0392b" },
  contradiction_found: { label: "Contradiction found", color: "#c0392b" },
};

function PendingApproval({ showToast }) {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState({});

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/stories/pending").then((res) => setStories(res.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const approve = async (id) => {
    try {
      await api.put(`/admin/stories/${id}/approve`, { notes: notes[id] || null });
      showToast("Approved - now live to users");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  const reject = async (id) => {
    try {
      await api.put(`/admin/stories/${id}/reject`, { notes: notes[id] || null });
      showToast("Rejected - will not be shown to users");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  if (loading) return <Loader text="Loading pending stories..." />;
  if (stories.length === 0) return <div className="empty-state">Nothing waiting for approval right now.</div>;

  return (
    <div>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, marginBottom: 16 }}>
        Every story requires explicit approval before it reaches users or emails. Flags below explain why each story needs your review.
      </p>
      {stories.map((s) => (
        <div key={s.id} className="story-card" style={{ cursor: "default" }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            <span className="category-chip">{s.category_slug}</span>
            {s.verification_flags.map((flag) => {
              const meta = FLAG_LABELS[flag] || { label: flag, color: "#888" };
              return (
                <span key={flag} style={{
                  fontSize: 11, fontWeight: 600, color: "#fff", background: meta.color,
                  padding: "2px 9px", borderRadius: 10, textTransform: "uppercase", letterSpacing: 0.3,
                }}>{meta.label}</span>
              );
            })}
          </div>
          <h3 className="story-headline">{s.headline}</h3>
          <p className="story-summary">{s.summary}</p>
          {s.headline_hi && (
            <p className="story-summary" style={{ fontStyle: "italic", color: "var(--ink-faint)" }}>
              हिंदी: {s.headline_hi} — {s.summary_hi}
            </p>
          )}
          <div style={{ fontSize: 12, color: "var(--ink-faint)", marginBottom: 8 }}>
            Confidence: {(s.confidence_score * 100).toFixed(0)}% · Similarity to source: {(s.max_source_similarity * 100).toFixed(0)}%
            {s.generator_model && <> · Generator: {s.generator_model}</>}
            {s.verifier_model && <> · Verifier: {s.verifier_model}</>}
          </div>
          {s.verifier_report && (
            <div style={{ fontSize: 12, background: "#f7f5f0", padding: 8, borderRadius: 6, marginBottom: 8 }}>
              Verifier verdict: <strong>{s.verifier_report.overall_verdict}</strong>
              {s.verifier_report.unsupported_claims?.length > 0 && (
                <> · Unsupported: {s.verifier_report.unsupported_claims.join("; ")}</>
              )}
            </div>
          )}
          <div className="citation-row">
            {s.citations.map((c, i) => (
              <a key={i} href={c.url} target="_blank" rel="noopener noreferrer" className="citation-badge">🔗 {c.source_name}</a>
            ))}
          </div>
          <input
            placeholder="Optional note (why approved/rejected)..."
            style={{ width: "100%", marginTop: 10, fontSize: 13 }}
            onChange={(e) => setNotes({ ...notes, [s.id]: e.target.value })}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button className="icon-btn" onClick={() => approve(s.id)}>✓ Approve &amp; publish</button>
            <button className="icon-btn danger" onClick={() => reject(s.id)}>✕ Reject</button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------- Developers & API Keys ----------------
function DevelopersAndKeys({ showToast }) {
  const [developers, setDevelopers] = useState([]);
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [devForm, setDevForm] = useState({ email: "", password: "" });
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.get("/admin/developers"), api.get("/admin/api-keys")])
      .then(([devRes, keyRes]) => { setDevelopers(devRes.data); setKeys(keyRes.data); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const createDeveloper = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/developers", devForm);
      setDevForm({ email: "", password: "" });
      showToast("Developer account created - share the login with them directly");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  const revokeDeveloper = async (id) => {
    if (!confirm("Revoke this developer's access?")) return;
    try {
      await api.delete(`/admin/developers/${id}`);
      showToast("Developer access revoked");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  const createKey = async (e) => {
    e.preventDefault();
    if (!keyName) return;
    try {
      const res = await api.post("/admin/api-keys", { name: keyName });
      setNewKey(res.data.raw_key);
      setKeyName("");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  const revokeKey = async (id) => {
    try {
      await api.delete(`/admin/api-keys/${id}`);
      showToast("API key revoked");
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  if (loading) return <Loader text="Loading..." />;

  return (
    <div>
      <h3 style={{ fontFamily: "var(--serif)", marginBottom: 8 }}>Developer accounts</h3>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, marginBottom: 12 }}>
        Read-only access to stats/sources/settings/pending stories, plus full access to the sandboxed
        test API - never real user data, never real emails.
      </p>
      <form onSubmit={createDeveloper} className="admin-form-row">
        <input type="email" placeholder="developer@example.com" value={devForm.email} onChange={(e) => setDevForm({ ...devForm, email: e.target.value })} />
        <input type="password" placeholder="Temporary password" value={devForm.password} onChange={(e) => setDevForm({ ...devForm, password: e.target.value })} />
        <button className="btn-secondary" type="submit">Create developer account</button>
      </form>
      <table className="admin-table" style={{ marginBottom: 30 }}>
        <thead><tr><th>Email</th><th>Joined</th><th></th></tr></thead>
        <tbody>
          {developers.map((d) => (
            <tr key={d.id}>
              <td>{d.email}</td>
              <td>{new Date(d.created_at).toLocaleDateString()}</td>
              <td><button className="icon-btn danger" onClick={() => revokeDeveloper(d.id)}>Revoke</button></td>
            </tr>
          ))}
          {developers.length === 0 && <tr><td colSpan={3} style={{ color: "var(--ink-faint)" }}>No developer accounts yet.</td></tr>}
        </tbody>
      </table>

      <h3 style={{ fontFamily: "var(--serif)", marginBottom: 8 }}>API keys</h3>
      <p style={{ color: "var(--ink-faint)", fontSize: 13, marginBottom: 12 }}>
        For a developer's own scripts/tools to call the sandboxed <code>/api/v1/*</code> endpoints directly.
      </p>
      {newKey && (
        <div style={{ background: "#111", color: "#fff", padding: 14, borderRadius: 8, marginBottom: 14, fontSize: 13 }}>
          <strong>Copy this now - it won't be shown again:</strong>
          <div style={{ fontFamily: "monospace", marginTop: 6, wordBreak: "break-all" }}>{newKey}</div>
          <button className="icon-btn" style={{ marginTop: 8 }} onClick={() => setNewKey(null)}>Done, I've copied it</button>
        </div>
      )}
      <form onSubmit={createKey} className="admin-form-row">
        <input placeholder="Key name, e.g. 'Dev laptop'" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
        <button className="btn-secondary" type="submit">Generate API key</button>
      </form>
      <table className="admin-table">
        <thead><tr><th>Name</th><th>Prefix</th><th>Status</th><th>Last used</th><th></th></tr></thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td><code>{k.key_prefix}...</code></td>
              <td>{k.is_active ? <span className="tag-ok">Active</span> : <span className="tag-error">Revoked</span>}</td>
              <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}</td>
              <td>{k.is_active && <button className="icon-btn danger" onClick={() => revokeKey(k.id)}>Revoke</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------- Audit Log ----------------
function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/admin/audit-log").then((res) => setLogs(res.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader text="Loading audit log..." />;

  return (
    <table className="admin-table">
      <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Notes</th></tr></thead>
      <tbody>
        {logs.map((l) => (
          <tr key={l.id}>
            <td>{new Date(l.created_at).toLocaleString()}</td>
            <td>{l.actor}</td>
            <td>{l.action}</td>
            <td>{l.entity_type}{l.entity_id ? ` #${l.entity_id}` : ""}</td>
            <td style={{ color: "var(--ink-faint)", maxWidth: 280 }}>{l.notes}</td>
          </tr>
        ))}
        {logs.length === 0 && <tr><td colSpan={5} style={{ color: "var(--ink-faint)" }}>No activity recorded yet.</td></tr>}
      </tbody>
    </table>
  );
}

// ---------------- Users ----------------
function UsersTab({ showToast }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.get("/admin/users").then((res) => setUsers(res.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleActive = async (id) => {
    try {
      await api.put(`/admin/users/${id}/toggle-active`);
      load();
    } catch (err) { showToast(err.friendlyMessage); }
  };

  if (loading) return <Loader text="Loading users..." />;

  return (
    <table className="admin-table">
      <thead><tr><th>Email</th><th>Role</th><th>Sign-in</th><th>Onboarded</th><th>Status</th><th>Joined</th><th></th></tr></thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id}>
            <td>{u.email}</td>
            <td>{u.role}</td>
            <td>{u.auth_provider === "google" ? "Google" : "Email"}</td>
            <td>{u.onboarded ? "Yes" : "No"}</td>
            <td>{u.is_active ? <span className="tag-ok">Active</span> : <span className="tag-error">Deactivated</span>}</td>
            <td>{new Date(u.created_at).toLocaleDateString()}</td>
            <td>
              {u.role !== "admin" && (
                <button className="icon-btn" onClick={() => toggleActive(u.id)}>
                  {u.is_active ? "Deactivate" : "Reactivate"}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
