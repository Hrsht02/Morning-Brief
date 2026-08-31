import { useEffect, useState } from "react";
import api from "../api";
import Loader from "../components/Loader";

export default function CountrySources() {
  const [sources,setSources]=useState([]); const [countries,setCountries]=useState([]); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const load=()=>api.get("/admin/sources").then(r=>setSources(r.data));
  useEffect(()=>{Promise.all([load(),api.get("/admin/countries")]).then(([,c])=>setCountries(c.data.supported)).catch(e=>setError(e.friendlyMessage||"Couldn't load source controls")).finally(()=>setLoading(false));},[]);
  const setCountry=async(s,c)=>{try{await api.put(`/admin/sources/${s.id}`,{country_code:c});await load();}catch(e){setError(e.friendlyMessage||"Couldn't update source");}};
  if(loading)return <Loader text="Loading country/source controls..."/>;
  return <div className="admin-page"><div className="admin-title">Country & Source Management</div><p style={{color:"var(--ink-faint)",fontSize:13}}>Assign each source to its primary editorial country. GLOBAL sources remain available to every supported reader.</p>{error&&<div className="error-text">{error}</div>}<table className="admin-table"><thead><tr><th>Source</th><th>Country</th><th>Active</th><th>Risk</th></tr></thead><tbody>{sources.map(s=><tr key={s.id}><td>{s.name}</td><td><select value={s.country_code||"GLOBAL"} onChange={e=>setCountry(s,e.target.value)}>{countries.map(c=><option key={c.code} value={c.code}>{c.name} ({c.code})</option>)}<option value="GLOBAL">Global</option></select></td><td>{s.is_active?"Active":"Paused"}</td><td>{s.legal_risk_level}</td></tr>)}</tbody></table></div>;
}
