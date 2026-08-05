import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, AppShell } from "@cpg-to-acp/ui-shared";
import { AppRoutes } from "./routes";

const navItems = [
  { label: "New Care Plan", path: "/" },
  { label: "Care Plans", path: "/plans" },
  { label: "System Status", path: "/status" },
];

export function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AppShell navItems={navItems} brandText="ACP Writer">
          <AppRoutes />
        </AppShell>
      </BrowserRouter>
    </ThemeProvider>
  );
}
