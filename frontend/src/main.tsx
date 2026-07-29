import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { DesktopShell } from "./app/DesktopShell";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DesktopShell />
  </StrictMode>,
);
