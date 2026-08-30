import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuthStore } from "../stores/auth";

export type UserRole = "ADMIN" | "MANAGER" | "INBOUND" | "OUTBOUND" | "WAREHOUSE" | "VIEWER";

export type CurrentUserScope = {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
  warehouse_scope_mode: "ALL" | "SELECTED";
  customer_scope_mode: "ALL" | "SELECTED";
  warehouse_ids: number[];
  customer_ids: number[];
};

const WRITE_WAREHOUSE: UserRole[] = ["ADMIN", "MANAGER", "INBOUND", "WAREHOUSE"];
const WRITE_OUTBOUND: UserRole[] = ["ADMIN", "MANAGER", "OUTBOUND", "WAREHOUSE"];

export function usePermissions() {
  const token = useAuthStore((s) => s.accessToken);
  const [me, setMe] = useState<CurrentUserScope | null>(null);

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    let cancelled = false;
    api.get<CurrentUserScope>("/users/me").then((res) => {
      if (!cancelled) setMe(res.data);
    }).catch(() => {
      if (!cancelled) setMe(null);
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return useMemo(() => {
    const role = me?.role;
    const canWriteWarehouse = !!role && WRITE_WAREHOUSE.includes(role);
    const canWriteOutbound = !!role && WRITE_OUTBOUND.includes(role);
    return {
      me,
      role,
      canView: !!me,
      canWriteWarehouse,
      canWriteOutbound,
      canManageUsers: role === "ADMIN",
      canCreateLoad: canWriteOutbound,
      canManageWorkOrder: canWriteWarehouse,
      canManageException: canWriteWarehouse,
      warehouseIds: me?.warehouse_ids ?? [],
      warehouseScopeMode: me?.warehouse_scope_mode ?? "ALL",
      canAccessWarehouse: (warehouseId?: number | null) => {
        if (!me) return false;
        if (me.warehouse_scope_mode === "ALL" || me.role === "ADMIN") return true;
        return warehouseId != null && me.warehouse_ids.includes(warehouseId);
      },
    };
  }, [me]);
}
