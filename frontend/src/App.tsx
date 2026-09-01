import { Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";
import { AppLayout } from "./layouts/AppLayout";
const InboundPage = lazy(() => import("./pages/InboundPage").then(m => ({ default: m.InboundPage })));
const InventoryPage = lazy(() => import("./pages/InventoryPage").then(m => ({ default: m.InventoryPage })));
const ImportHistoryPage = lazy(() => import("./pages/ImportHistoryPage").then(m => ({ default: m.ImportHistoryPage })));
const AdminDataUploadPage = lazy(() => import("./pages/AdminDataUploadPage").then(m => ({ default: m.AdminDataUploadPage })));
const FBAPage = lazy(() => import("./pages/FBAPage").then(m => ({ default: m.FBAPage })));
const OutboundDispatchPage = lazy(() => import("./pages/OutboundDispatchWorkbenchPage").then(m => ({ default: m.OutboundDispatchWorkbenchPage })));
const ContainerTrackingPage = lazy(() => import("./pages/ContainerTrackingPage").then(m => ({ default: m.ContainerTrackingPage })));
const PickingPage = lazy(() => import("./pages/PickingPage").then(m => ({ default: m.PickingPage })));
const BOLPage = lazy(() => import("./pages/BOLPage").then(m => ({ default: m.BOLPage })));
const LoadsPage = lazy(() => import("./pages/LoadsPage").then(m => ({ default: m.LoadsPage })));
const WorkOrdersPage = lazy(() => import("./pages/WorkOrdersPage").then(m => ({ default: m.WorkOrdersPage })));
const TroubleShootPage = lazy(() => import("./pages/TroubleShootPage").then(m => ({ default: m.TroubleShootPage })));
const OperationsDashboardPage = lazy(() => import("./pages/OperationsDashboardPage").then(m => ({ default: m.OperationsDashboardPage })));
const DocumentsPage = lazy(() => import("./pages/DocumentsPage").then(m => ({ default: m.DocumentsPage })));
const CompanySettingsPage = lazy(() => import("./pages/CompanySettingsPage").then(m => ({ default: m.CompanySettingsPage })));
import { LoginPage } from "./pages/LoginPage";
import { useAuthStore } from "./stores/auth";
import "./inventory.css";
import "./fba.css";
import "./outbound.css";
export default function App() {
  const token = useAuthStore((s) => s.accessToken);
  if (!token) return <LoginPage />;
  return (
    <Suspense fallback={<div className="page-loading">Loading…</div>}><Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<OperationsDashboardPage />} />
        <Route path="/inbound" element={<InboundPage />} />
        <Route path="/container-tracking" element={<ContainerTrackingPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/fba" element={<FBAPage />} />
        <Route path="/outbound/dispatch" element={<OutboundDispatchPage />} />
        <Route path="/outbound/picking" element={<PickingPage />} />
        <Route path="/outbound/picking-history" element={<PickingPage history />} />
        <Route path="/outbound/bol" element={<BOLPage />} />
        <Route path="/loads" element={<LoadsPage />} />
        <Route path="/work-orders" element={<WorkOrdersPage />} />
        <Route path="/trouble-shoot" element={<TroubleShootPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/import-history" element={<ImportHistoryPage />} />
        <Route path="/admin/data-upload" element={<AdminDataUploadPage />} />
        <Route path="/settings/:slug" element={<CompanySettingsPage />} />
        <Route path="/company/:slug" element={<CompanySettingsPage />} />
        <Route path="*" element={<Navigate to="/inbound" replace />} />
      </Route>
    </Routes></Suspense>
  );
}
