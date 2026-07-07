
import { createRoot } from "react-dom/client";
import App from "./app/App.tsx";
import "./styles/index.css";
// Leaflet core CSS — must come before any Leaflet component is rendered
import "leaflet/dist/leaflet.css";

  createRoot(document.getElementById("root")!).render(<App />);
  