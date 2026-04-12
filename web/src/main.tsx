import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { captureAttribution } from "./lib/attribution";

// Capture UTM params and referrer on first landing (before React mounts)
captureAttribution();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
