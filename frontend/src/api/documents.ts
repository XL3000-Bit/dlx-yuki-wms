import { api } from "./client";

export type DocumentType =
  | "BOL"
  | "POD"
  | "DELIVERY_RECEIPT"
  | "WAREHOUSE"
  | "EXCEPTION_ATTACHMENT"
  | "GENERAL";
export interface OperationalDocument {
  id: number;
  document_no: string;
  document_type: DocumentType;
  status: string;
  version: number;
  original_filename: string;
  content_type: string;
  file_size: number | null;
  is_generated: boolean;
  title: string | null;
  notes: string | null;
  warehouse_id: number;
  customer_id: number | null;
  inbound_id: number | null;
  load_id: number | null;
  outbound_id: number | null;
  bol_id: number | null;
  work_order_id: number | null;
  operational_exception_id: number | null;
  container_tracking_id: number | null;
  created_at: string;
}
export interface DocumentEvent {
  id: number;
  event_type: string;
  actor_user_id: number | null;
  message: string | null;
  created_at: string;
}
export const getDocuments = async (params: Record<string, unknown>) =>
  (await api.get("/documents", { params })).data as {
    data: OperationalDocument[];
    meta: { total: number };
  };
export const getDocument = async (id: number) =>
  (await api.get(`/documents/${id}`)).data as OperationalDocument;
export const getDocumentEvents = async (id: number) =>
  (await api.get(`/documents/${id}/events`)).data as DocumentEvent[];
export const uploadDocument = async (
  values: Record<string, unknown>,
  file: File,
) => {
  const body = new FormData();
  body.append("file", file);
  Object.entries(values).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") body.append(k, String(v));
  });
  return (await api.post("/documents", body)).data as OperationalDocument;
};
export const archiveDocument = async (id: number) =>
  (await api.post(`/documents/${id}/archive`)).data as OperationalDocument;
export async function downloadDocument(doc: OperationalDocument) {
  const r = await api.get(`/documents/${doc.id}/download`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.original_filename;
  a.click();
  URL.revokeObjectURL(url);
}
