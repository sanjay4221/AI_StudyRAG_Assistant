/**
 * js/auth.js
 * ----------
 * JWT token helpers used by app.js.
 * Loaded as a plain <script> before app.js in index.html.
 */

const Auth = {
  /** Get the stored JWT token */
  getToken() {
    return localStorage.getItem("token");
  },

  /** Get logged-in user info */
  getUser() {
    return {
      user_id:   localStorage.getItem("user_id"),
      email:     localStorage.getItem("email"),
      full_name: localStorage.getItem("full_name") || "Student",
      is_admin:  localStorage.getItem("is_admin") === "true",
    };
  },

  /** Returns true if the logged-in user is an admin */
  isAdmin() {
    return localStorage.getItem("is_admin") === "true";
  },

  /** Add Authorization header to fetch options */
  headers() {
    return {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${this.getToken()}`,
    };
  },

  /** Log out — clear storage and go to login page */
  logout() {
    localStorage.clear();
    window.location.href = "/";
  },

  /** Redirect to login if no token found */
  requireAuth() {
    if (!this.getToken()) {
      window.location.href = "/";
    }
  },
};
