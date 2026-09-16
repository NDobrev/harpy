import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Gallery } from "./Gallery";
import "./tokens.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <Gallery />
  </StrictMode>,
);
