import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
// Bundled (not fetched from a font CDN): the tool runs offline. Barlow
// Semi Condensed is the UI/label face, JetBrains Mono the data face.
import "@fontsource/barlow-semi-condensed/400.css";
import "@fontsource/barlow-semi-condensed/600.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
