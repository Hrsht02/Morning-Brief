import { useEffect, useMemo, useState } from "react";
import api from "../api";
import Loader from "../components/Loader";

function todayInIndia(){return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());}

export default function ApprovedNews() {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayInIndia());

  useEffect(() => {
    api.get("/admin/stories/approved?limit=500")
      .then((res) => setStories(res.data))
      .catch((err) => setError(err.friendlyMessage || "Couldn't load approved stories"))
      .finally(() => setLoading(false));
  }, []);

  const dates = useMemo(() => [...new Set(stories.map((s) => s.edition_date).filter(Boolean))].sort().reverse(), [stories]);
  const filtered = useMemo(() => stories.filter((s) => !selectedDate || s.edition_date === selectedDate), [stories, selectedDate]);

  if (loading) return <Loader text="Loading approved news..." />;
  return (
    <div className="admin-page">
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"end",gap:16,flexWrap:"wrap"}}>
        <div>
          <div className="admin-title">Approved News</div>
          <p style={{ color: "var(--ink-faint)", fontSize: 13, marginBottom: 0 }}>
            Approved production stories eligible for the selected edition and email delivery.
          </p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <label style={{fontSize:12,color:"var(--ink-faint)"}}>Edition date</label>
          <select value={selectedDate} onChange={(e)=>setSelectedDate(e.target.value)} style={{padding:"8px 10px",border:"1px solid var(--border)",borderRadius:8,background:"var(--surface)",color:"var(--ink)"}}>
            <option value={todayInIndia()}>Today ({todayInIndia()})</option>
            {dates.filter((d)=>d!==todayInIndia()).map((d)=><option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      </div>
      {error && <div className="error-text">{error}</div>}
      <div style={{marginTop:14,padding:"10px 12px",border:"1px solid var(--border)",borderRadius:9,fontSize:12.5,color:"var(--ink-faint)"}}>
        Showing <strong>{selectedDate}</strong> · <strong>{filtered.length}</strong> approved {filtered.length===1?"story":"stories"}. Stories from older editions are kept as history and are not used as today's email fallback.
      </div>
      <div className="admin-table-wrap" style={{marginTop:14}}>
        <table className="admin-table">
          <thead><tr><th>Date</th><th>Country</th><th>Category</th><th>Headline</th><th>Confidence</th><th>Originality</th></tr></thead>
          <tbody>
            {filtered.map((s) => (
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
      {!filtered.length && <div className="empty-state">No approved production stories for {selectedDate}. They may still be processing or waiting for approval.</div>}
    </div>
  );
}
