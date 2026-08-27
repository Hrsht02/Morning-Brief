import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_URL, timeout: 20000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("mb_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // Normalize error shape so components can rely on `err.friendlyMessage`
    // instead of digging through axios's nested error object every time.
    if (err.response) {
      const detail = err.response.data?.detail;
      err.friendlyMessage =
        typeof detail === "string"
          ? detail
          : err.response.status === 401
          ? "Your session has expired. Please log in again."
          : "Something went wrong. Please try again.";
      if (err.response.status === 401) {
        localStorage.removeItem("mb_token");
      }
    } else if (err.request) {
      err.friendlyMessage = "Couldn't reach the server. Check your connection and try again.";
    } else {
      err.friendlyMessage = "Something went wrong. Please try again.";
    }
    return Promise.reject(err);
  }
);

export default api;
