import {
  HistoryOutlined,
  DatabaseOutlined,
  TruckOutlined,
  ImportOutlined,
  LogoutOutlined,
  SettingOutlined,
  DashboardOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
  HomeOutlined,
  WarningOutlined,
  UserOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { Avatar, Button, Layout, Menu, Space } from "antd";
import { useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useCurrentUser } from "../hooks/usePermissions";
import { GlobalSearch } from "../components/GlobalSearch";
import { NotificationCenter } from "../components/NotificationCenter";
import { CompanyMenu } from "../components/CompanyMenu";

const { Header, Sider, Content } = Layout;
const SIDER_KEY = "dlx_wms:sider_collapsed";

function openKeysFor(path: string) {
  if (path.startsWith("/inbound") || path.startsWith("/container-tracking")) return ["inbound"];
  if (path.startsWith("/inventory") || path.startsWith("/fba")) return ["warehouse"];
  if (path.startsWith("/outbound") || path.startsWith("/loads")) return ["outbound"];
  if (path.startsWith("/work-orders") || path.startsWith("/trouble-shoot") || path.startsWith("/documents")) return ["ops"];
  if (path.startsWith("/import-history") || path.startsWith("/admin")) return ["tools"];
  return [];
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDER_KEY) === "1");
  const nav = useNavigate();
  const loc = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const me = useCurrentUser();
  const isAdmin = me.data?.role === "ADMIN";
  const selected = loc.pathname;
  const initialOpen = useMemo(() => openKeysFor(loc.pathname), [loc.pathname]);
  const [openKeys, setOpenKeys] = useState<string[]>(initialOpen);

  const toggleSider = () => {
    setCollapsed((value) => {
      const next = !value;
      localStorage.setItem(SIDER_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    <Layout className={`app-layout ${collapsed ? "is-sider-collapsed" : ""}`}>
      <Sider width={220} collapsedWidth={64} collapsed={collapsed} collapsible trigger={null} className="brand-sider">
        <div className="brand">
          <div className="brand-mark">Y</div>
          {!collapsed && (
            <span>
              Yuki WMS
              <small>DLX OPERATIONS</small>
            </span>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          inlineIndent={16}
          selectedKeys={[selected]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={setOpenKeys}
          onClick={(e) => { if (!e.key.startsWith("g-")) nav(e.key); }}
          items={[
            { key: "/dashboard", icon: <DashboardOutlined />, label: "Dashboard" },
            {
              key: "inbound", icon: <ImportOutlined />, label: "InBound",
              children: [
                { key: "/inbound", label: "Receiving" },
                { key: "/container-tracking", label: "Container Tracking" },
              ],
            },
            {
              key: "warehouse", icon: <HomeOutlined />, label: "Warehouse",
              children: [
                { key: "/inventory", icon: <DatabaseOutlined />, label: "Inventory" },
                { key: "/fba", icon: <TruckOutlined />, label: "FBA" },
              ],
            },
            {
              key: "outbound", icon: <TruckOutlined />, label: "OutBound",
              children: [
                { key: "/outbound/dispatch", label: "Dispatch" },
                { key: "/outbound/picking", label: "Picking List" },
                { key: "/outbound/picking-history", label: "Picking History" },
                { key: "/outbound/bol", label: "BOL" },
                { key: "/loads", label: "Loads" },
              ],
            },
            {
              key: "ops", icon: <WarningOutlined />, label: "Operations",
              children: [
                { key: "/work-orders", icon: <HistoryOutlined />, label: "Work Orders" },
                { key: "/trouble-shoot", label: "Trouble Shoot" },
                { key: "/documents", icon: <FileTextOutlined />, label: "Documents & POD" },
              ],
            },
            {
              key: "tools", icon: <SettingOutlined />, label: "Tools",
              children: [
                { key: "/import-history", icon: <HistoryOutlined />, label: "Import History" },
                ...(isAdmin ? [{ key: "/admin/data-upload", icon: <CloudUploadOutlined />, label: "Data Upload" }] : []),
              ],
            },
          ]}
        />
        <div className="sider-footer">
          <Button className="signout-btn" icon={<LogoutOutlined />} onClick={logout} block>
            {!collapsed && "Sign out"}
          </Button>
        </div>
        <button type="button" className="sider-rail" aria-label={collapsed ? "Expand menu" : "Collapse menu"} title={collapsed ? "Expand menu" : "Collapse menu"} onClick={toggleSider}>
          {collapsed ? <RightOutlined /> : <LeftOutlined />}
        </button>
      </Sider>
      <Layout>
        <Header className="topbar">
          <GlobalSearch />
          <Space size={8} className="topbar-actions">
            <NotificationCenter />
            <CompanyMenu />
            <Avatar size={28} icon={<UserOutlined />} className="topbar-avatar" />
          </Space>
        </Header>
        <Content className={`content ${loc.pathname === "/outbound/dispatch" ? "content-workbench" : ""}`}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
