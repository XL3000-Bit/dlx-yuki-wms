import { api } from "./client";

export type OperationalDocument = {
  id: number;
  document_no: string;
  document_type: string;
  status: string;
  file_name: string;
  original_file_name: string;
  mime_type: string;
  file_size: number;
  warehouse_id: number;
  warehouse_code?: string;
  load_id?: number | null;
  outbound_id?: number | null;
  bol_id?: number | null;
  work_order_id?: number | null;
  exception_id?: number | null;
  container_tracking_id?: number | null;
  description?: string | null;
  version: number;
  uploaded_by: number;
  uploader_name?: string | null;
  uploaded_at: string;
  references: { kind: string; id: number; label: string }[];
  pod_status?: string | null;
};

export const getDocuments = (params: Record<string, string | number | undefined>) =>
  api.get<{ data: OperationalDocument[]; meta: { page: number; per_page: number; total: number } }>("/documents", { params }).then((r) => r.data);

export const getDocument = (id: number) => api.get<OperationalDocument>(`/documents/${id}`).then((r) => r.data);

export const getDocumentEvents = (id: number) => api.get<{ data: any[] }>(`/documents/${id}/events`).then((r) => r.data);

export const archiveDocument = (id: number) => api.post<OperationalDocument>(`/documents/${id}/archive`).then((r) => r.data);

export async function uploadDocument(payload: { file: File; document_type: string; description?: string } & Record<string, number | string | undefined>) {
  const body = new FormData();
  body.append("file", payload.file);
  body.append("document_type", payload.document_type);
  if (payload.description) body.append("description", String(payload.description));
  for (const key of ["warehouse_id", "load_id", "outbound_id", "bol_id", "work_order_id", "exception_id", "container_tracking_id"]) {
    if (payload[key] != null && payload[key] !== "") body.append(key, String(payload[key]));
  }
  return api.post<OperationalDocument>("/documents/upload", body).then((r) => r.data);
}

export async function downloadDocument(id: number, filename: string) {
  const res = await api.get(`/documents/${id}/download`, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
