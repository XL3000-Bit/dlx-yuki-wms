import {
  HistoryOutlined,
  DatabaseOutlined,
  TruckOutlined,
  ImportOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  DashboardOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
  HomeOutlined,
  WarningOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Avatar, Button, Layout, Menu, Space } from "antd";
import { useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useCurrentUser } from "../hooks/usePermissions";
import { GlobalSearch } from "../components/GlobalSearch";
import { NotificationCenter } from "../components/NotificationCenter";

const { Header, Sider, Content } = Layout;

function openKeysFor(path: string) {
  if (path.startsWith("/inbound") || path.startsWith("/container-tracking")) return ["inbound"];
  if (path.startsWith("/inventory") || path.startsWith("/fba")) return ["warehouse"];
  if (path.startsWith("/outbound") || path.startsWith("/loads")) return ["outbound"];
  if (path.startsWith("/work-orders") || path.startsWith("/trouble-shoot") || path.startsWith("/documents")) return ["ops"];
  if (path.startsWith("/import-history") || path.startsWith("/admin")) return ["tools"];
  return [];
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const me = useCurrentUser();
  const isAdmin = me.data?.role === "ADMIN";
  const selected = loc.pathname;
  const defaultOpen = useMemo(() => openKeysFor(loc.pathname), [loc.pathname]);

  return (
    <Layout className="app-layout">
      <Sider width={220} collapsedWidth={64} collapsed={collapsed} className="brand-sider">
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
          selectedKeys={[selected]}
          defaultOpenKeys={defaultOpen}
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
          <Button className="sider-toggle" type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed(!collapsed)} />
        </div>
      </Sider>
      <Layout>
        <Header className="topbar">
          <GlobalSearch />
          <Space size={8} className="topbar-actions">
            <NotificationCenter />
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
