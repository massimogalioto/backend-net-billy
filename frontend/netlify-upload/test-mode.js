// TEMPORARY TEST MODE - remove when real authentication is implemented.
// This only bypasses the static frontend preview; it never creates an identity,
// sends a tenant ID, or stores credentials.
const TEST_MODE = true;
const TEST_BACKEND_URL = "https://backend-net-billy-production.up.railway.app";

if (TEST_MODE) {
  sessionStorage.setItem("energia-backend", JSON.stringify({ url: TEST_BACKEND_URL, key: "" }));
  if (location.pathname === "/accedi/" || location.pathname === "/registrati/") {
    location.replace("/workspace/");
  }
}
