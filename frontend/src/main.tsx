import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { DesktopShell } from "./app/DesktopShell";
import "./design/tokens.css";
import "./design/base.css";
import "./design/buttons.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DesktopShell />
  </StrictMode>,
);
