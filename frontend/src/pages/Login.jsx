import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import GoogleSignInButton from "../components/GoogleSignInButton";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/edition");
    } catch (err) {
      setError(err.friendlyMessage || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-title">Welcome back</div>
        <div className="auth-subtitle">Log in to read today's edition</div>

        <GoogleSignInButton
          onSuccess={() => navigate("/edition")}
          onError={(msg) => setError(msg)}
        />
        <div style={{ textAlign: "center", color: "var(--ink-faint)", fontSize: 13, margin: "4px 0 16px" }}>
          or use your email
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Logging in..." : "Log in"}
          </button>
          {error && <div className="error-text">{error}</div>}
        </form>
        <div className="switch-link">
          New here? <Link to="/signup"><button type="button">Create an account</button></Link>
        </div>
      </div>
    </div>
  );
}
