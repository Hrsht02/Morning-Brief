import { useEffect, useState } from "react";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import Loader from "../components/Loader";

export default function Preferences() {
  const { user, refreshUser } = useAuth();
  const [categories, setCategories] = useState([]); const [countries, setCountries] = useState([]);
  const [selected, setSelected] = useState([]); const [country, setCountry] = useState("IN"); const [language, setLanguage] = useState("en"); const [emailConsent, setEmailConsent] = useState(false);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  useEffect(() => { Promise.all([api.get("/categories"), api.get("/users/supported-countries"), api.get("/legal/consent")]).then(([c, cs, consent]) => { setCategories(c.data.filter(x => x.slug !== "general" && !x.parent_slug)); setCountries(cs.data.countries); setEmailConsent(Boolean(consent.data.email_news_opt_in)); }).catch(err => setError(err.friendlyMessage || "Couldn't load preferences")).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (user) { setSelected(user.categories || []); setCountry(user.country_code || "IN"); setLanguage(user.content_language || "en"); } }, [user]);
  const toggleCategory = slug => setSelected(prev => prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]);
  const handleSave = async () => { setSaving(true); setError(""); setMessage(""); try { const timezone = user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; await api.put("/users/preferences", { timezone, country_code: country, send_hour: 6, send_minute: 0, category_slugs: selected, content_language: language }); await api.put("/legal/consent", { email_news_opt_in: emailConsent }); await refreshUser(); setMessage(emailConsent ? "Preferences saved and news emails enabled." : "Preferences saved. News emails are disabled; you can opt in again anytime."); } catch (err) { setError(err.friendlyMessage || "Couldn't save preferences"); } finally { setSaving(false); } };
  if (loading) return <Loader text="Loading your preferences..." />;
  return <div className="onboarding-page">
    <div className="onboarding-step-title">Your preferences</div><div className="onboarding-step-sub">Your country affects local-news ranking. Your timezone is used for your account and local-date handling; production delivery is controlled by the administrator.</div>
    <div className="chip-grid">{countries.map(c => <button key={c.code} className={`chip-option ${country === c.code ? "selected" : ""}`} onClick={() => setCountry(c.code)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>भाषा / Language</div><div className="chip-grid"><button className={`chip-option ${language === "en" ? "selected" : ""}`} onClick={() => setLanguage("en")} type="button">English</button><button className={`chip-option ${language === "hi" ? "selected" : ""}`} onClick={() => setLanguage("hi")} type="button">हिंदी (Hindi)</button></div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>Categories</div><div className="chip-grid">{categories.map(c => <button key={c.slug} className={`chip-option ${selected.includes(c.slug) ? "selected" : ""}`} onClick={() => toggleCategory(c.slug)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title" style={{ fontSize: 20 }}>Email delivery</div><label style={{ display:"flex", gap:10, alignItems:"flex-start", fontSize:13, lineHeight:1.5, margin:"10px 0 18px" }}><input type="checkbox" checked={emailConsent} onChange={e => setEmailConsent(e.target.checked)} style={{ marginTop:3 }} /><span>Receive Morning Brief news emails. You can withdraw this consent at any time.</span></label>
    <div className="onboarding-step-sub" style={{ marginBottom: 16 }}>Delivery is controlled by the administrator's production schedule. Your categories, country and language control which stories are selected for you.</div>
    <button className="btn-primary" onClick={handleSave} disabled={saving}>{saving ? "Saving..." : "Save preferences"}</button>{message && <div style={{ color: "var(--success)", fontSize: 13, marginTop: 10, textAlign: "center" }}>{message}</div>}{error && <div className="error-text">{error}</div>}
  </div>;
}
