import { useEffect, useState } from "react";
import api from "../api";
import Loader from "../components/Loader";

export default function ApprovedNews() {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/admin/stories/approved?limit=500")
      .then((res) => setStories(res.data))
      .catch((err) => setError(err.friendlyMessage || "Couldn't load approved stories"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader text="Loading approved news..." />;
  return (
    <div className="admin-page">
      <div className="admin-title">All Approved News</div>
      <p style={{ color: "var(--ink-faint)", fontSize: 13 }}>
        Production stories that passed the publication gate and are eligible for reader editions and email delivery.
      </p>
      {error && <div className="error-text">{error}</div>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead><tr><th>Date</th><th>Country</th><th>Category</th><th>Headline</th><th>Confidence</th><th>Originality</th></tr></thead>
          <tbody>
            {stories.map((s) => (
              <tr key={s.id}>
                <td>{s.edition_date || "—"}</td>
                <td>{s.country_code || "GLOBAL"}</td>
                <td>{s.category_slug}</td>
                <td><strong>{s.headline}</strong><br /><span style={{ color: "var(--ink-faint)", fontSize: 12 }}>{s.summary}</span></td>
                <td>{Math.round((s.confidence_score || 0) * 100)}%</td>
                <td>{s.originality_rewrite_applied ? "Rewritten" : "Originality check passed"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!stories.length && <div className="empty-state">No approved production stories found.</div>}
    </div>
  );
}
