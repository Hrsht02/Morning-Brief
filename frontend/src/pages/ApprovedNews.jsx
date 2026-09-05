import { useEffect, useMemo, useState } from "react";
import api from "../api";
import Loader from "../components/Loader";

function todayInIndia(){return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());}

export default function ApprovedNews() {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayInIndia());
  const [status, setStatus] = useState("approved");
  const [minConfidence, setMinConfidence] = useState("");
  const [maxSimilarity, setMaxSimilarity] = useState("");
  const [benchmark, setBenchmark] = useState({min_confidence:0.55,max_similarity:0.20,apply_mode:"upcoming"});
  const [savingBenchmark, setSavingBenchmark] = useState(false);
  const [benchmarkMessage, setBenchmarkMessage] = useState("");

  const load = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({status, edition_date:selectedDate || ""});
      const [storiesRes, benchmarkRes] = await Promise.all([
        api.get(`/admin/quality/stories?${params.toString()}`),
        api.get("/admin/quality/benchmark"),
      ]);
      setStories(storiesRes.data || []);
      setBenchmark(benchmarkRes.data || benchmark);
      setError("");
    } catch (err) {
      setError(err.friendlyMessage || "Couldn't load quality data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [status, selectedDate]);

  const dates = useMemo(() => [...new Set(stories.map((s) => s.edition_date).filter(Boolean))].sort().reverse(), [stories]);
  const filtered = useMemo(() => stories.filter((s) => {
    const confidence = Number(s.confidence_score || 0);
    const similarity = Number(s.max_source_similarity || 0);
    return (minConfidence === "" || confidence >= Number(minConfidence)/100) &&
      (maxSimilarity === "" || similarity <= Number(maxSimilarity)/100);
  }), [stories, minConfidence, maxSimilarity]);

  const saveBenchmark = async () => {
    try {
      setSavingBenchmark(true);
      setBenchmarkMessage("");
      const res = await api.put("/admin/quality/benchmark", {
        min_confidence:Number(benchmark.min_confidence),
        max_similarity:Number(benchmark.max_similarity),
        apply_mode:benchmark.apply_mode,
      });
      setBenchmark(res.data);
      setBenchmarkMessage(res.data.current_edition
        ? `Benchmark saved. Current edition: ${res.data.current_edition.approved} newly approved, ${res.data.current_edition.held_for_review} held.`
        : "Benchmark saved for the selected scope.");
      await load();
    } catch (err) {
      setBenchmarkMessage(err.friendlyMessage || "Couldn't save benchmark");
    } finally {
      setSavingBenchmark(false);
    }
  };

  if (loading) return <Loader text="Loading quality data..." />;
  return (
    <div className="admin-page">
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"end",gap:16,flexWrap:"wrap"}}>
        <div>
          <div className="admin-title">Approved News & Quality</div>
          <p style={{ color:"var(--ink-faint)", fontSize:13, marginBottom:0 }}>
            Filter ingested stories by confidence and source-similarity, and control the automatic publication benchmark.
          </p>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <label style={{fontSize:12,color:"var(--ink-faint)"}}>Edition</label>
          <select value={selectedDate} onChange={(e)=>setSelectedDate(e.target.value)} style={{padding:"8px 10px",border:"1px solid var(--border)",borderRadius:8,background:"var(--surface)",color:"var(--ink)"}}>
            <option value="">All dates</option>
            <option value={todayInIndia()}>Today ({todayInIndia()})</option>
            {dates.filter((d)=>d!==todayInIndia()).map((d)=><option key={d} value={d}>{d}</option>)}
          </select>
          <select value={status} onChange={(e)=>setStatus(e.target.value)} style={{padding:"8px 10px",border:"1px solid var(--border)",borderRadius:8,background:"var(--surface)",color:"var(--ink)"}}>
            <option value="approved">Approved</option>
            <option value="pending">Pending</option>
            <option value="all">All</option>
          </select>
        </div>
      </div>

      {error && <div className="error-text">{error}</div>}

      <section style={{marginTop:14,padding:14,border:"1px solid var(--border)",borderRadius:12,background:"var(--surface)"}}>
        <strong>Quality filters</strong>
        <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:10,marginTop:10}}>
          <label style={{fontSize:12.5}}>Confidence at least (%)
            <input type="number" min="0" max="100" value={minConfidence} placeholder="Any" onChange={(e)=>setMinConfidence(e.target.value)} style={{display:"block",width:"100%",marginTop:5}} />
          </label>
          <label style={{fontSize:12.5}}>Similarity at most (%)
            <input type="number" min="0" max="100" value={maxSimilarity} placeholder="Any" onChange={(e)=>setMaxSimilarity(e.target.value)} style={{display:"block",width:"100%",marginTop:5}} />
          </label>
        </div>
        <div style={{fontSize:11.5,color:"var(--ink-faint)",marginTop:7}}>Lower similarity is better. Higher confidence is better.</div>
      </section>

      <section style={{marginTop:14,padding:14,border:"1px solid var(--border)",borderRadius:12,background:"var(--surface)"}}>
        <div style={{display:"flex",justifyContent:"space-between",gap:10,flexWrap:"wrap"}}>
          <div>
            <strong>Automatic publication benchmark</strong>
            <div style={{fontSize:11.5,color:"var(--ink-faint)",marginTop:4}}>A story can auto-publish only when it meets both numbers and no safety/editorial blocking check fails.</div>
          </div>
          <span style={{fontSize:11,fontWeight:700,padding:"4px 9px",borderRadius:12,border:"1px solid var(--border)"}}>Current: {Math.round(Number(benchmark.min_confidence)*100)}% confidence · {Math.round(Number(benchmark.max_similarity)*100)}% similarity</span>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:10,marginTop:10}}>
          <label style={{fontSize:12.5}}>Minimum confidence (%)
            <input type="number" min="0" max="100" value={Math.round(Number(benchmark.min_confidence)*100)} onChange={(e)=>setBenchmark({...benchmark,min_confidence:Number(e.target.value)/100})} style={{display:"block",width:"100%",marginTop:5}} />
          </label>
          <label style={{fontSize:12.5}}>Maximum similarity (%)
            <input type="number" min="0" max="100" value={Math.round(Number(benchmark.max_similarity)*100)} onChange={(e)=>setBenchmark({...benchmark,max_similarity:Number(e.target.value)/100})} style={{display:"block",width:"100%",marginTop:5}} />
          </label>
          <label style={{fontSize:12.5}}>Apply benchmark to
            <select value={benchmark.apply_mode} onChange={(e)=>setBenchmark({...benchmark,apply_mode:e.target.value})} style={{display:"block",width:"100%",marginTop:5}}>
              <option value="upcoming">Upcoming ingestion only</option>
              <option value="current">Already ingested today</option>
              <option value="current_and_upcoming">Already ingested today + upcoming</option>
            </select>
          </label>
        </div>
        <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap",marginTop:10}}>
          <button className="btn-secondary" onClick={saveBenchmark} disabled={savingBenchmark}>{savingBenchmark?"Saving…":"Save benchmark"}</button>
          {benchmarkMessage && <span style={{fontSize:12,color:"var(--ink-faint)"}}>{benchmarkMessage}</span>}
        </div>
        <div style={{fontSize:11.5,color:"var(--ink-faint)",marginTop:8}}>
          “Already ingested today” re-checks stored confidence/similarity for today's stories. It does not regenerate their text. Safety blocks such as failed verification remain blocking.
        </div>
      </section>

      <div style={{marginTop:14,padding:"10px 12px",border:"1px solid var(--border)",borderRadius:9,fontSize:12.5,color:"var(--ink-faint)"}}>
        Showing <strong>{filtered.length}</strong> stories after the selected filters.
      </div>
      <div className="admin-table-wrap" style={{marginTop:14}}>
        <table className="admin-table">
          <thead><tr><th>Date</th><th>Status</th><th>Country</th><th>Category</th><th>Headline</th><th>Confidence</th><th>Similarity</th><th>Flags</th></tr></thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.id}>
                <td>{s.edition_date || "—"}</td>
                <td>{s.publication_status}</td>
                <td>{s.country_code || "GLOBAL"}</td>
                <td>{s.category_slug}</td>
                <td><strong>{s.headline}</strong><br /><span style={{color:"var(--ink-faint)",fontSize:12}}>{s.summary}</span></td>
                <td>{Math.round((s.confidence_score || 0)*100)}%</td>
                <td>{Math.round((s.max_source_similarity || 0)*100)}%</td>
                <td style={{maxWidth:280,fontSize:11}}>{s.verification_flags || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!filtered.length && <div className="empty-state">No stories match the current filters.</div>}
    </div>
  );
}
