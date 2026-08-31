import { useEffect, useState } from "react";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import Loader from "../components/Loader";

export default function Preferences() {
  const { user, refreshUser } = useAuth();
  const [categories, setCategories] = useState([]); const [countries, setCountries] = useState([]);
  const [selected, setSelected] = useState([]); const [country, setCountry] = useState("IN"); const [sendHour, setSendHour] = useState(6); const [language, setLanguage] = useState("en");
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  useEffect(() => { Promise.all([api.get("/categories"), api.get("/users/supported-countries")]).then(([c, cs]) => { setCategories(c.data.filter(x => x.slug !== "general" && !x.parent_slug)); setCountries(cs.data.countries); }).catch(err => setError(err.friendlyMessage)).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (user) { setSelected(user.categories || []); setCountry(user.country_code || "IN"); setSendHour(user.send_hour ?? 6); setLanguage(user.content_language || "en"); } }, [user]);
  const toggleCategory = slug => setSelected(prev => prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]);
  const handleSave = async () => { setSaving(true); setError(""); setMessage(""); try { const timezone = user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; await api.put("/users/preferences", { timezone, country_code: country, send_hour: Number(sendHour), send_minute: 0, category_slugs: selected, content_language: language }); await refreshUser(); setMessage("Preferences saved."); } catch (err) { setError(err.friendlyMessage || "Couldn't save preferences"); } finally { setSaving(false); } };
  if (loading) return <Loader text="Loading your preferences..." />;
  return <div className="onboarding-page">
    <div className="onboarding-step-title">Your preferences</div><div className="onboarding-step-sub">Country affects local-news ranking and fallback behavior.</div>
    <div className="chip-grid">{countries.map(c => <button key={c.code} className={`chip-option ${country === c.code ? "selected" : ""}`} onClick={() => setCountry(c.code)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>भाषा / Language</div><div className="chip-grid"><button className={`chip-option ${language === "en" ? "selected" : ""}`} onClick={() => setLanguage("en")} type="button">English</button><button className={`chip-option ${language === "hi" ? "selected" : ""}`} onClick={() => setLanguage("hi")} type="button">हिंदी (Hindi)</button></div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>Categories</div><div className="chip-grid">{categories.map(c => <button key={c.slug} className={`chip-option ${selected.includes(c.slug) ? "selected" : ""}`} onClick={() => toggleCategory(c.slug)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>Delivery time</div><div className="time-row"><select value={sendHour} onChange={e => setSendHour(e.target.value)}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{h === 0 ? "12:00 AM" : h < 12 ? `${h}:00 AM` : h === 12 ? "12:00 PM" : `${h - 12}:00 PM`}</option>)}</select><span style={{ color: "var(--ink-faint)", fontSize: 13 }}>({user?.timezone})</span></div>
    <button className="btn-primary" onClick={handleSave} disabled={saving}>{saving ? "Saving..." : "Save preferences"}</button>{message && <div style={{ color: "var(--success)", fontSize: 13, marginTop: 10, textAlign: "center" }}>{message}</div>}{error && <div className="error-text">{error}</div>}
  </div>;
}
