import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import Loader from "../components/Loader";

export default function Onboarding() {
  const [categories, setCategories] = useState([]); const [countries, setCountries] = useState([]);
  const [selected, setSelected] = useState([]); const [country, setCountry] = useState("IN");
  const [sendHour, setSendHour] = useState(6); const [language, setLanguage] = useState("en");
  const [emailConsent, setEmailConsent] = useState(false);
  const [loading, setLoading] = useState(true); const [submitting, setSubmitting] = useState(false); const [error, setError] = useState("");
  const { refreshUser } = useAuth(); const navigate = useNavigate();
  useEffect(() => {
    Promise.all([api.get("/categories"), api.get("/users/supported-countries")])
      .then(([cats, cs]) => { setCategories(cats.data.filter(c => c.slug !== "general" && !c.parent_slug)); setCountries(cs.data.countries); })
      .catch(err => setError(err.friendlyMessage || "Couldn't load setup options"))
      .finally(() => setLoading(false));
  }, []);
  const toggleCategory = slug => setSelected(prev => prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]);
  const handleFinish = async () => {
    if (!emailConsent) { setError("Please opt in to Morning Brief emails to enable delivery. You can withdraw this consent later."); return; }
    setSubmitting(true); setError("");
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      await api.post("/users/onboarding", { timezone, country_code: country, send_hour: Number(sendHour), send_minute: 0, category_slugs: selected, content_language: language });
      await api.put("/legal/consent", { email_news_opt_in: true });
      await refreshUser(); navigate("/edition");
    } catch (err) { setError(err.friendlyMessage || "Something went wrong"); } finally { setSubmitting(false); }
  };
  if (loading) return <Loader text="Setting things up..." />;
  return <div className="onboarding-page">
    <div className="onboarding-step-title">Where are you based?</div>
    <div className="onboarding-step-sub">We use this to put relevant local news first. Unsupported countries safely fall back to global news.</div>
    <div className="chip-grid">{countries.map(c => <button key={c.code} className={`chip-option ${country === c.code ? "selected" : ""}`} onClick={() => setCountry(c.code)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title">भाषा / Language</div>
    <div className="chip-grid"><button className={`chip-option ${language === "en" ? "selected" : ""}`} onClick={() => setLanguage("en")} type="button">English</button><button className={`chip-option ${language === "hi" ? "selected" : ""}`} onClick={() => setLanguage("hi")} type="button">हिंदी (Hindi)</button></div>
    <div className="onboarding-step-title">What are you into?</div>
    <div className="onboarding-step-sub">Pick categories to prioritize. We'll still include some broader news.</div>
    <div className="chip-grid">{categories.map(c => <button key={c.slug} className={`chip-option ${selected.includes(c.slug) ? "selected" : ""}`} onClick={() => toggleCategory(c.slug)} type="button">{c.name}</button>)}</div>
    <div className="onboarding-step-title" style={{ fontSize: 22 }}>When should we send it?</div>
    <div className="onboarding-step-sub">Your timezone is detected automatically. The default is 6 AM local time.</div>
    <div className="time-row"><select value={sendHour} onChange={e => setSendHour(e.target.value)}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{h === 0 ? "12:00 AM" : h < 12 ? `${h}:00 AM` : h === 12 ? "12:00 PM" : `${h - 12}:00 PM`}</option>)}</select><span style={{ color: "var(--ink-faint)", fontSize: 13 }}>({Intl.DateTimeFormat().resolvedOptions().timeZone})</span></div>
    <label style={{ display: "flex", gap: 10, alignItems: "flex-start", margin: "20px 0", fontSize: 13, lineHeight: 1.5 }}>
      <input type="checkbox" checked={emailConsent} onChange={e => setEmailConsent(e.target.checked)} style={{ marginTop: 3 }} />
      <span>I agree to receive Morning Brief news emails and understand that I can withdraw this consent at any time. See the <a href="/legal" target="_blank" rel="noreferrer">privacy notice</a>.</span>
    </label>
    <button className="btn-primary" onClick={handleFinish} disabled={submitting}>{submitting ? "Saving..." : "Start reading"}</button>
    {error && <div className="error-text">{error}</div>}
  </div>;
}
