import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// Installable, and openable offline. Registration is best-effort: a browser that
// refuses (private mode, unsupported) must still get a working page.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
