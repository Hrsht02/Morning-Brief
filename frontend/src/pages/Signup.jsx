import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import GoogleSignInButton from "../components/GoogleSignInButton";

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);
    try {
      await signup(email, password);
      navigate("/onboarding");
    } catch (err) {
      setError(err.friendlyMessage || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-title">Start your mornings informed</div>
        <div className="auth-subtitle">One calm email a day. Every story links back to its real source.</div>

        <GoogleSignInButton
          onSuccess={() => navigate("/onboarding")}
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
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
          </div>
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </button>
          {error && <div className="error-text">{error}</div>}
        </form>
        <div className="switch-link">
          Already have an account? <Link to="/login"><button type="button">Log in</button></Link>
        </div>
      </div>
    </div>
  );
}
