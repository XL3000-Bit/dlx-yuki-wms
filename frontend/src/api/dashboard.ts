import { api } from "./client";

export type OperationsDashboard = {
  filters: { warehouse_id: number | null; period: string; period_start: string; period_end: string };
  definitions: Record<string, string>;
  summary: Record<string, { value: number; kind: string; href: string; active?: number }>;
  loads: { created_in_period: number; status: Record<string, number>; active: number; completed_in_period: number; average_outbounds_per_active_load: number | null };
  work_orders: { status: Record<string, number>; priority_open: Record<string, number>; completed_today: number; completed_in_period: number; overdue: number; aging: Record<string, number>; funnel: { key: string; value: number }[] };
  exceptions: { status: Record<string, number>; severity_open: Record<string, number>; types_open: { type: string; count: number }[]; average_resolution_seconds: number | null; aging: Record<string, number> };
  warehouse_breakdown: { warehouse_id: number; warehouse_code: string; active_loads: number; open_work_orders: number; open_exceptions: number; critical_exceptions: number }[];
  attention: { kind: string; id: number; reference: string; status: string; severity_or_priority: string; age_hours: number; title: string; target_route: string }[];
  recent_activity: { created_at: string; kind: string; event_type: string; reference: string; actor_user_id: number | null; summary: string; target_route: string }[];
};

export const getOperationsDashboard = (params: Record<string, string | number | undefined>) =>
  api.get<OperationsDashboard>("/dashboard/operations", { params }).then((r) => r.data);
