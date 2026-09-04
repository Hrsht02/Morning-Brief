import { useEffect, useState } from "react";
import api from "../api";

export default function Legal() {
  const [data, setData] = useState(null); const [error, setError] = useState("");
  useEffect(() => { Promise.all([api.get("/legal/disclosure"), api.get("/legal/privacy-notice")]).then(([d,p]) => setData({ disclosure:d.data, privacy:p.data })).catch(e => setError(e.friendlyMessage || "Unable to load legal notices")); }, []);
  if (error) return <div className="page"><div className="error-text">{error}</div></div>;
  if (!data) return <div className="page">Loading...</div>;
  return <div className="page" style={{ maxWidth: 820 }}>
    <h1>Transparency & Privacy</h1>
    <section className="card"><h2>AI-generated content</h2><p>{data.disclosure.ai_disclosure}</p><p>{data.disclosure.source_policy}</p></section>
    <section className="card"><h2>Privacy notice</h2><p>{data.privacy.notice}</p><h3>Your controls</h3><ul>{data.privacy.rights.map(r => <li key={r}>{r}</li>)}</ul><p>Notice version: {data.privacy.version}</p></section>
  </div>;
}
