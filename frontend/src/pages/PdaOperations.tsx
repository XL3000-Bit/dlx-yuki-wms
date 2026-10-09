import {
  ArrowLeftOutlined,
  AuditOutlined,
  CheckCircleFilled,
  ExportOutlined,
  ImportOutlined,
  LogoutOutlined,
  ScanOutlined,
  SwapOutlined,
  WifiOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Input, Select } from "antd";
import axios from "axios";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getInbounds, receiveToInventory } from "../api/inbound";
import { adjustInventory, getInventory, moveInventory } from "../api/inventory";
import { getLocations, getWarehouses } from "../api/masterData";
import { completeOutbound, dispatchOutbound, getOutbounds } from "../api/outbound";
import { CameraScanner } from "../components/pda/CameraScanner";
import { usePermission } from "../hooks/usePermissions";
import { useAuthStore } from "../stores/auth";
import type { InboundRecord } from "../types/inbound";
import type { InventoryLot } from "../types/inventory";
import type { Location, Warehouse } from "../types/masterData";
import type { OutboundRecord } from "../types/outbound";

export type PdaMode = "inbound" | "outbound" | "pick" | "count" | "move";
type WorkMode = Exclude<PdaMode, "pick">;

const modeMeta: Record<PdaMode, { code: string; title: string; description: string; icon: ReactNode }> = {
  inbound: { code: "RECEIVE", title: "入库", description: "扫描入库单，确认收货入库", icon: <ImportOutlined /> },
  outbound: { code: "SHIP", title: "出库", description: "扫描出库单，确认发运与完成", icon: <ExportOutlined /> },
  pick: { code: "PICK", title: "拣货", description: "按库位和批次执行拣货", icon: <ScanOutlined /> },
  count: { code: "COUNT", title: "盘点", description: "扫描库位和批次，登记实盘数", icon: <AuditOutlined /> },
  move: { code: "MOVE", title: "移库", description: "扫描批次与目标库位完成移动", icon: <SwapOutlined /> },
};

function apiError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? "请求无效").join("；");
  }
  return "操作未完成，请检查网络后重试。";
}

function exact(value: string | null | undefined, expected: string) {
  return (value ?? "").trim().toUpperCase() === expected.trim().toUpperCase();
}

function makeCountNo() {
  const now = new Date();
  const pair = (value: number) => String(value).padStart(2, "0");
  const date = `${String(now.getFullYear()).slice(-2)}${pair(now.getMonth() + 1)}${pair(now.getDate())}`;
  return `CC${date}${String(now.getTime()).slice(-4)}`;
}

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function Header({ online }: { online: boolean }) {
  const logout = useAuthStore((state) => state.logout);
  return (
    <header className="pda-header">
      <div className="pda-brand"><span>Warehouse</span><small>WMS · PDA</small></div>
      <div className={`pda-network ${online ? "is-online" : "is-offline"}`}>
        <WifiOutlined /> {online ? "在线" : "离线"}
      </div>
      <Button type="text" aria-label="退出登录" icon={<LogoutOutlined />} onClick={logout} />
    </header>
  );
}

export function PdaOperations({ mode, onNavigate }: { mode: WorkMode | null; onNavigate: (mode: PdaMode | null) => void }) {
  const online = useOnline();
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const locations = useQuery({ queryKey: ["warehouse-locations"], queryFn: getLocations });

  return (
    <main className="pda-shell">
      <Header online={online} />
      {!online && <Alert banner type="warning" message="当前离线：除拣货外的库存操作需要联网后执行。" />}
      {!mode ? (
        <section className="pda-hub">
          <div className="pda-kicker">WAREHOUSE OPERATIONS</div>
          <h1>仓库作业</h1>
          <p>选择作业类型，使用设备扫码键或相机读取条码。</p>
          <div className="pda-module-grid">
            {(Object.keys(modeMeta) as PdaMode[]).map((key) => (
              <button type="button" key={key} className={`pda-module-card is-${key}`} onClick={() => onNavigate(key)}>
                <i>{modeMeta[key].icon}</i>
                <span><b>{modeMeta[key].title}</b><small>{modeMeta[key].description}</small></span>
                <em>{modeMeta[key].code}</em>
              </button>
            ))}
          </div>
          <div className="pda-code-note"><ScanOutlined /><span>编码基准：仓库 WH、库位 Location、入库 IB、出库 OB、拣货 PK、批次 LOT、盘点 CC、移库 MV。</span></div>
        </section>
      ) : (
        <OperationScreen
          key={mode}
          mode={mode}
          online={online}
          warehouses={warehouses.data ?? []}
          locations={locations.data ?? []}
          loadingMaster={warehouses.isLoading || locations.isLoading}
          masterError={warehouses.isError || locations.isError}
          onBack={() => onNavigate(null)}
        />
      )}
    </main>
  );
}

function OperationScreen({
  mode,
  online,
  warehouses,
  locations,
  loadingMaster,
  masterError,
  onBack,
}: {
  mode: WorkMode;
  online: boolean;
  warehouses: Warehouse[];
  locations: Location[];
  loadingMaster: boolean;
  masterError: boolean;
  onBack: () => void;
}) {
  const permissionName = mode === "inbound" ? "manage_inbound" : mode === "outbound" ? "manage_outbound" : "manage_warehouse";
  const permission = usePermission(permissionName);
  const [warehouseId, setWarehouseId] = useState<number | undefined>(() => {
    const saved = Number(localStorage.getItem("pda-warehouse-id"));
    return Number.isFinite(saved) && saved > 0 ? saved : undefined;
  });
  const warehouseLocations = useMemo(
    () => locations.filter((item) => item.warehouse_id === warehouseId && item.is_active),
    [locations, warehouseId],
  );
  const chooseWarehouse = (value: number) => {
    setWarehouseId(value);
    localStorage.setItem("pda-warehouse-id", String(value));
  };

  return (
    <>
      <section className="pda-operation-title">
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>功能菜单</Button>
        <div><span>{modeMeta[mode].code}</span><h1>{modeMeta[mode].title}作业</h1></div>
      </section>
      <section className="pda-operation-form">
        <label className="pda-field-label">作业仓库</label>
        <Select
          size="large"
          value={warehouseId}
          loading={loadingMaster}
          placeholder="选择仓库"
          onChange={chooseWarehouse}
          options={warehouses.filter((item) => item.is_active).map((item) => ({
            value: item.id,
            label: `${item.warehouse_code} · ${item.warehouse_name}`,
          }))}
        />
        {masterError && <Alert type="error" message="仓库与库位资料加载失败。" />}
        {permission.isError && <Alert type="error" message="无法验证当前账号权限。" />}
        {!permission.isLoading && !permission.allowed && <Alert type="warning" message="当前账号没有此项作业权限。" />}
        {mode === "inbound" && <InboundPanel key={warehouseId ?? "none"} warehouseId={warehouseId} enabled={online && permission.allowed} />}
        {mode === "outbound" && <OutboundPanel key={warehouseId ?? "none"} warehouseId={warehouseId} enabled={online && permission.allowed} />}
        {mode === "move" && <MovePanel key={warehouseId ?? "none"} warehouseId={warehouseId} locations={warehouseLocations} enabled={online && permission.allowed} />}
        {mode === "count" && <CountPanel key={warehouseId ?? "none"} warehouseId={warehouseId} locations={warehouseLocations} enabled={online && permission.allowed} />}
      </section>
    </>
  );
}

function ScanField({ label, placeholder, value, disabled, busy, onChange, onSubmit }: {
  label: string;
  placeholder: string;
  value: string;
  disabled?: boolean;
  busy?: boolean;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
}) {
  return (
    <div className="pda-scan-block">
      <label className="pda-field-label">{label}</label>
      <Input
        size="large"
        className="pda-primary-input"
        prefix={<ScanOutlined />}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(event) => onChange(event.target.value.toUpperCase())}
        onPressEnter={() => onSubmit(value)}
      />
      <Button block size="large" type="primary" loading={busy} disabled={disabled || !value.trim()} onClick={() => onSubmit(value)}>查询条码</Button>
      {!disabled && <CameraScanner onDetected={(code) => { onChange(code.toUpperCase()); onSubmit(code); }} />}
    </div>
  );
}

function ResultMessage({ error, success, onClose }: { error: string | null; success: string | null; onClose: () => void }) {
  if (error) return <Alert showIcon closable type="error" message={error} onClose={onClose} />;
  if (success) return <Alert showIcon closable type="success" message={success} onClose={onClose} />;
  return null;
}

function InboundPanel({ warehouseId, enabled }: { warehouseId?: number; enabled: boolean }) {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [record, setRecord] = useState<InboundRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const lookup = async (raw: string) => {
    const value = raw.trim();
    if (!warehouseId) return setError("请先选择作业仓库。");
    if (!value) return;
    setBusy(true); setError(null); setSuccess(null); setRecord(null);
    try {
      const result = await getInbounds({ q: value, warehouse_id: warehouseId, per_page: 50 });
      const found = result.data.find((item) => exact(item.inbound_no, value));
      if (!found) throw new Error("未找到与条码完全匹配的入库单。");
      setRecord(found);
    } catch (requestError) {
      setError(requestError instanceof Error && !axios.isAxiosError(requestError) ? requestError.message : apiError(requestError));
    } finally { setBusy(false); }
  };

  const receive = async () => {
    if (!record) return;
    if (!record.location) return setError("此入库单尚未设置收货库位，请先在桌面端补充库位。");
    setBusy(true); setError(null);
    try {
      const lot = await receiveToInventory(record.id);
      setSuccess(`入库完成，库存批次：${lot.lot_no}`);
      setRecord({ ...record, inventory_created: true, inventory_lot_id: lot.id });
      void queryClient.invalidateQueries({ queryKey: ["inbounds"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    } catch (requestError) { setError(apiError(requestError)); }
    finally { setBusy(false); }
  };

  return (
    <>
      <ScanField label="入库单条码" placeholder="扫描 IB 单号" value={code} onChange={setCode} onSubmit={(value) => void lookup(value)} disabled={!enabled} busy={busy} />
      <ResultMessage error={error} success={success} onClose={() => { setError(null); setSuccess(null); }} />
      {record && <div className="pda-record-card">
        <h2>{record.inbound_no}<span>{record.status_name}</span></h2>
        <dl><div><dt>柜号</dt><dd>{record.container_number}</dd></div><div><dt>收货库位</dt><dd>{record.location?.code ?? "未设置"}</dd></div><div><dt>托盘</dt><dd>{record.pallet_qty}</dd></div><div><dt>箱数</dt><dd>{record.carton_qty}</dd></div></dl>
        <Button block size="large" type="primary" loading={busy} disabled={!enabled || record.inventory_created} onClick={() => void receive()}>{record.inventory_created ? "已生成库存" : "确认收货入库"}</Button>
      </div>}
    </>
  );
}

function OutboundPanel({ warehouseId, enabled }: { warehouseId?: number; enabled: boolean }) {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [record, setRecord] = useState<OutboundRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const lookup = async (raw: string) => {
    const value = raw.trim();
    if (!warehouseId) return setError("请先选择作业仓库。");
    setBusy(true); setError(null); setSuccess(null); setRecord(null);
    try {
      const result = await getOutbounds({ q: value, warehouse_id: warehouseId, per_page: 50 });
      const found = result.data.find((item) => exact(item.ob_no, value));
      if (!found) throw new Error("未找到与条码完全匹配的出库单。");
      setRecord(found);
    } catch (requestError) { setError(requestError instanceof Error && !axios.isAxiosError(requestError) ? requestError.message : apiError(requestError)); }
    finally { setBusy(false); }
  };

  const transition = async (action: "dispatch" | "complete") => {
    if (!record) return;
    setBusy(true); setError(null); setSuccess(null);
    try {
      const updated = action === "dispatch" ? await dispatchOutbound(record.id) : await completeOutbound(record.id);
      setRecord(updated);
      setSuccess(action === "dispatch" ? "出库单已确认发运。" : "出库单已完成，库存扣减已确认。");
      void queryClient.invalidateQueries({ queryKey: ["outbounds"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    } catch (requestError) { setError(apiError(requestError)); }
    finally { setBusy(false); }
  };

  return <>
    <ScanField label="出库单条码" placeholder="扫描 OB 单号" value={code} onChange={setCode} onSubmit={(value) => void lookup(value)} disabled={!enabled} busy={busy} />
    <ResultMessage error={error} success={success} onClose={() => { setError(null); setSuccess(null); }} />
    {record && <div className="pda-record-card">
      <h2>{record.ob_no}<span>{record.status_name}</span></h2>
      <dl><div><dt>类型</dt><dd>{record.ob_type}</dd></div><div><dt>分配批次</dt><dd>{record.allocation_count}</dd></div><div><dt>托盘</dt><dd>{record.total_pallet_qty}</dd></div><div><dt>箱数</dt><dd>{record.total_carton_qty}</dd></div></dl>
      {record.status < 3 && <Alert showIcon type="info" message="请先在桌面端完成库存分配并确认出库单。" />}
      <div className="pda-button-stack">
        <Button block size="large" type="primary" loading={busy} disabled={!enabled || record.status !== 3} onClick={() => void transition("dispatch")}>确认发运</Button>
        <Button block size="large" loading={busy} disabled={!enabled || record.status !== 4} onClick={() => void transition("complete")}>完成出库</Button>
      </div>
    </div>}
  </>;
}

function MovePanel({ warehouseId, locations, enabled }: { warehouseId?: number; locations: Location[]; enabled: boolean }) {
  const queryClient = useQueryClient();
  const [lotCode, setLotCode] = useState("");
  const [targetCode, setTargetCode] = useState("");
  const [lot, setLot] = useState<InventoryLot | null>(null);
  const [target, setTarget] = useState<Location | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const lookupLot = async (raw: string) => {
    const value = raw.trim();
    if (!warehouseId) return setError("请先选择作业仓库。");
    setBusy(true); setError(null); setSuccess(null); setLot(null);
    try {
      const result = await getInventory({ q: value, warehouse_id: warehouseId, per_page: 50 });
      const found = result.data.find((item) => exact(item.lot_no, value));
      if (!found) throw new Error("未找到与条码完全匹配的库存批次。");
      setLot(found);
    } catch (requestError) { setError(requestError instanceof Error && !axios.isAxiosError(requestError) ? requestError.message : apiError(requestError)); }
    finally { setBusy(false); }
  };
  const lookupTarget = (raw: string) => {
    const found = locations.find((item) => exact(item.location_code, raw));
    setTarget(found ?? null);
    setError(found ? null : "目标库位不存在、已停用或不属于当前仓库。");
  };
  const move = async () => {
    if (!lot || !target) return;
    if (lot.location?.id === target.id) return setError("目标库位不能与当前库位相同。");
    setBusy(true); setError(null); setSuccess(null);
    const moveNo = `MV${makeCountNo().slice(2)}`;
    try {
      const updated = await moveInventory(lot.id, { to_location_id: target.id, remark: `${moveNo} PDA移库` });
      setLot(updated);
      setSuccess(`移库完成：${moveNo}，目标库位 ${target.location_code}`);
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    } catch (requestError) { setError(apiError(requestError)); }
    finally { setBusy(false); }
  };
  return <>
    <ScanField label="库存批次" placeholder="扫描 LOT 批次号" value={lotCode} onChange={setLotCode} onSubmit={(value) => void lookupLot(value)} disabled={!enabled} busy={busy} />
    {lot && <div className="pda-record-card pda-record-compact"><h2>{lot.lot_no}<span>{lot.location?.code ?? "无库位"}</span></h2><p>可用：{lot.available_pallet_qty} 托 / {lot.available_carton_qty} 箱</p></div>}
    <ScanField label="目标库位" placeholder="扫描目标库位码" value={targetCode} onChange={setTargetCode} onSubmit={lookupTarget} disabled={!enabled || !lot} />
    {target && <Alert showIcon type="info" message={`目标库位：${target.location_code} · ${target.location_name}`} />}
    <ResultMessage error={error} success={success} onClose={() => { setError(null); setSuccess(null); }} />
    <Button className="pda-confirm-button" block size="large" type="primary" loading={busy} disabled={!enabled || !lot || !target} onClick={() => void move()}>确认移库</Button>
  </>;
}

function CountPanel({ warehouseId, locations, enabled }: { warehouseId?: number; locations: Location[]; enabled: boolean }) {
  const queryClient = useQueryClient();
  const [locationCode, setLocationCode] = useState("");
  const [location, setLocation] = useState<Location | null>(null);
  const [lotCode, setLotCode] = useState("");
  const [lot, setLot] = useState<InventoryLot | null>(null);
  const [pallets, setPallets] = useState("");
  const [cartons, setCartons] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const lookupLocation = (raw: string) => {
    const found = locations.find((item) => exact(item.location_code, raw));
    setLocation(found ?? null); setLot(null);
    setError(found ? null : "库位不存在、已停用或不属于当前仓库。");
  };
  const lookupLot = async (raw: string) => {
    if (!warehouseId || !location) return setError("请先扫描盘点库位。");
    setBusy(true); setError(null); setSuccess(null); setLot(null);
    try {
      const result = await getInventory({ q: raw.trim(), warehouse_id: warehouseId, location_id: location.id, per_page: 50 });
      const found = result.data.find((item) => exact(item.lot_no, raw));
      if (!found) throw new Error("该库位中没有与条码完全匹配的库存批次。");
      setLot(found); setPallets(found.available_pallet_qty); setCartons(found.available_carton_qty);
    } catch (requestError) { setError(requestError instanceof Error && !axios.isAxiosError(requestError) ? requestError.message : apiError(requestError)); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!lot || !location) return;
    const actualPallets = Number(pallets);
    const actualCartons = Number(cartons);
    if (!Number.isFinite(actualPallets) || !Number.isFinite(actualCartons) || actualPallets < 0 || actualCartons < 0) return setError("实盘数量必须是大于或等于 0 的数字。");
    const palletDelta = actualPallets - Number(lot.available_pallet_qty);
    const cartonDelta = actualCartons - Number(lot.available_carton_qty);
    if (palletDelta === 0 && cartonDelta === 0) return setSuccess("盘点相符，无需调整库存。");
    setBusy(true); setError(null); setSuccess(null);
    const countNo = makeCountNo();
    try {
      const updated = await adjustInventory(lot.id, {
        pallet_delta: palletDelta,
        carton_delta: cartonDelta,
        weight_delta: 0,
        cbm_delta: 0,
        reason: "COUNT_CORRECTION",
        remark: `${countNo} PDA盘点；库位 ${location.location_code}`,
      });
      setLot(updated);
      setSuccess(`盘点已过账：${countNo}；差异 ${palletDelta >= 0 ? "+" : ""}${palletDelta} 托 / ${cartonDelta >= 0 ? "+" : ""}${cartonDelta} 箱`);
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    } catch (requestError) { setError(apiError(requestError)); }
    finally { setBusy(false); }
  };
  return <>
    <ScanField label="盘点库位" placeholder="扫描库位码" value={locationCode} onChange={setLocationCode} onSubmit={lookupLocation} disabled={!enabled} />
    {location && <Alert showIcon type="info" message={`当前库位：${location.location_code} · ${location.location_name}`} />}
    <ScanField label="库存批次" placeholder="扫描 LOT 批次号" value={lotCode} onChange={setLotCode} onSubmit={(value) => void lookupLot(value)} disabled={!enabled || !location} busy={busy} />
    {lot && <div className="pda-count-entry">
      <div><label className="pda-field-label">实盘可用托盘数</label><Input size="large" inputMode="decimal" value={pallets} onChange={(event) => setPallets(event.target.value)} /></div>
      <div><label className="pda-field-label">实盘可用箱数</label><Input size="large" inputMode="decimal" value={cartons} onChange={(event) => setCartons(event.target.value)} /></div>
      <p>账面可用：{lot.available_pallet_qty} 托 / {lot.available_carton_qty} 箱</p>
    </div>}
    <ResultMessage error={error} success={success} onClose={() => { setError(null); setSuccess(null); }} />
    <Button className="pda-confirm-button" block size="large" type="primary" loading={busy} disabled={!enabled || !lot} onClick={() => void confirm()}>确认盘点并过账</Button>
  </>;
}
