import { Route, Routes } from "react-router-dom";
import { IpsView } from "@app/pages/IpsView";
import { GenerationProgress } from "@app/pages/GenerationProgress";
import { CarePlanReview } from "@app/pages/CarePlanReview";
import { CarePlanList } from "@app/pages/CarePlanList";
import { SystemStatus } from "@app/pages/SystemStatus";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<IpsView />} />
      <Route path="/generate/:runId" element={<GenerationProgress />} />
      <Route path="/plans" element={<CarePlanList />} />
      <Route path="/plans/:id" element={<CarePlanReview />} />
      <Route path="/status" element={<SystemStatus />} />
    </Routes>
  );
}
