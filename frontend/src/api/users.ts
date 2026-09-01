import { api } from "./client";

export type UserRole = "ADMIN" | "MANAGER" | "INBOUND" | "OUTBOUND" | "WAREHOUSE" | "VIEWER";

export type ManagedUser = {
  id: number;
  username: string;
  display_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  warehouse_scope_mode: "ALL" | "SELECTED";
  customer_scope_mode: "ALL" | "SELECTED";
};

export const listUsers = async () => (await api.get<ManagedUser[]>("/users")).data;
export const createUser = async (payload: Record<string, unknown>) => (await api.post<ManagedUser>("/users", payload)).data;
export const updateUser = async (id: number, payload: Record<string, unknown>) => (await api.patch<ManagedUser>(`/users/${id}`, payload)).data;
