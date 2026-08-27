import { useEffect, useRef, useState } from "react";
import api from "../api";
import { useAuth } from "../context/AuthContext";

/**
 * Renders Google's own Sign-In button, but ONLY if the backend reports a
 * configured GOOGLE_CLIENT_ID - if you haven't set one up yet, this
 * component simply renders nothing rather than showing a broken button.
 * Loads Google's script lazily so pages that never need it don't pay for it.
 */
export default function GoogleSignInButton({ onSuccess, onError }) {
  const [clientId, setClientId] = useState(null);
  const buttonRef = useRef(null);
  const { googleLogin } = useAuth();

  useEffect(() => {
    api.get("/auth/google-client-id")
      .then((res) => setClientId(res.data.google_client_id))
      .catch(() => setClientId(null));
  }, []);

  useEffect(() => {
    if (!clientId) return;

    const scriptId = "google-identity-script";
    const initialize = () => {
      if (!window.google || !buttonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          try {
            await googleLogin(response.credential);
            onSuccess?.();
          } catch (err) {
            onError?.(err.friendlyMessage || "Google sign-in failed");
          }
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline", size: "large", width: 320, text: "continue_with",
      });
    };

    if (document.getElementById(scriptId)) {
      initialize();
    } else {
      const script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = initialize;
      document.body.appendChild(script);
    }
  }, [clientId, googleLogin, onSuccess, onError]);

  if (!clientId) return null; // Google Sign-In not configured on the backend - fail silently, not broken

  return (
    <div style={{ display: "flex", justifyContent: "center", margin: "16px 0" }}>
      <div ref={buttonRef} />
    </div>
  );
}
