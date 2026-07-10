import React from "react";
import ReactDOM from "react-dom/client";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/federation.css";
import "./styles/app.css";
import App from "./App";

document.documentElement.dataset.repo = "spiderweb-pr";
document.documentElement.dataset.theme = "dark";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
