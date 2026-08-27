import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { useAuth } from "../context/AuthContext";
import Loader from "../components/Loader";

export default function Onboarding() {
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState([]);
  const [sendHour, setSendHour] = useState(6);
  const [language, setLanguage] = useState("en");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const { refreshUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/categories")
      .then((res) => setCategories(res.data.filter((c) => c.slug !== "general" && !c.parent_slug)))
      .catch((err) => setError(err.friendlyMessage))
      .finally(() => setLoading(false));
  }, []);

  const toggleCategory = (slug) => {
    setSelected((prev) => (prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]));
  };

  const handleFinish = async () => {
    setSubmitting(true);
    setError("");
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      await api.post("/users/onboarding", {
        timezone,
        send_hour: Number(sendHour),
        send_minute: 0,
        category_slugs: selected,
        content_language: language,
      });
      await refreshUser();
      navigate("/edition");
    } catch (err) {
      setError(err.friendlyMessage || "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Loader text="Setting things up..." />;

  return (
    <div className="onboarding-page">
      <div className="onboarding-step-title">भाषा / Language</div>
      <div className="onboarding-step-sub">Read your news in English or Hindi — switch anytime in Preferences.</div>
      <div className="chip-grid">
        <button className={`chip-option ${language === "en" ? "selected" : ""}`} onClick={() => setLanguage("en")} type="button">English</button>
        <button className={`chip-option ${language === "hi" ? "selected" : ""}`} onClick={() => setLanguage("hi")} type="button">हिंदी (Hindi)</button>
      </div>

      <div className="onboarding-step-title">What are you into?</div>
      <div className="onboarding-step-sub">
        Pick a few categories to prioritize — or skip this and we'll send a balanced mix. You can change this anytime.
      </div>
      <div className="chip-grid">
        {categories.map((c) => (
          <button
            key={c.slug}
            className={`chip-option ${selected.includes(c.slug) ? "selected" : ""}`}
            onClick={() => toggleCategory(c.slug)}
            type="button"
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="onboarding-step-title" style={{ fontSize: 22 }}>When should we send it?</div>
      <div className="onboarding-step-sub">We detected your timezone automatically. Most readers pick 6-7 AM.</div>
      <div className="time-row">
        <select value={sendHour} onChange={(e) => setSendHour(e.target.value)}>
          {Array.from({ length: 24 }, (_, h) => (
            <option key={h} value={h}>
              {h === 0 ? "12:00 AM" : h < 12 ? `${h}:00 AM` : h === 12 ? "12:00 PM" : `${h - 12}:00 PM`}
            </option>
          ))}
        </select>
        <span style={{ color: "var(--ink-faint)", fontSize: 13 }}>
          ({Intl.DateTimeFormat().resolvedOptions().timeZone})
        </span>
      </div>

      <button className="btn-primary" onClick={handleFinish} disabled={submitting}>
        {submitting ? "Saving..." : "Start reading"}
      </button>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
