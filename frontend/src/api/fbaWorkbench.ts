import { api } from "./client";
import type {
  FBAWorkbenchDetail,
  FBAWorkbenchParams,
  FBAWorkbenchResponse,
} from "../types/fbaWorkbench";
export const getFBAWorkbench = async (params: FBAWorkbenchParams) =>
  (await api.get<FBAWorkbenchResponse>("/fba/workbench", { params })).data;
export const getFBAWorkbenchDetail = async (id: number) =>
  (await api.get<FBAWorkbenchDetail>(`/fba/${id}/workbench-detail`)).data;
export async function exportFBAWorkbench(
  params: FBAWorkbenchParams,
  selected?: number[],
) {
  const r = selected?.length
    ? await api.post("/fba/workbench/export-selected", { fba_ids: selected }, { responseType: "blob" })
    : await api.get("/fba/files/export.xlsx", { params, responseType: "blob" });
  const u = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = u;
  a.download = "FBA_Workbench.xlsx";
  a.click();
  URL.revokeObjectURL(u);
}
export interface FBABatchResponse {
  action: string;
  successful: number;
  skipped: number;
  failed: number;
  results: Array<{ fba_id: number; status: string; reason?: string | null }>;
}
export const runFBAWorkbenchBatch = async (action: string, fba_ids: number[]) => (await api.post<FBABatchResponse>('/fba/workbench/batch', { action, fba_ids })).data;
