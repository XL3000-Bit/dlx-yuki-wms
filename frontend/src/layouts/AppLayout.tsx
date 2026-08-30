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
} from "@ant-design/icons";
import { Button, Layout, Menu, Typography } from "antd";
import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { GlobalSearch } from "../components/GlobalSearch";
import { NotificationCenter } from "../components/NotificationCenter";
const { Header, Sider, Content } = Layout;
export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  const logout = useAuthStore((s) => s.logout);
  return (
    <Layout className="app-layout">
      <Sider
        width={212}
        collapsedWidth={60}
        collapsed={collapsed}
        className="brand-sider"
      >
        <div className="brand">
          <b>DLX</b>
          {!collapsed && (
            <span>
              Yuki WMS <small>VERSION 3</small>
            </span>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[loc.pathname]}
          onClick={(e) => nav(e.key)}
          items={[
            { key: "/dashboard", icon: <DashboardOutlined />, label: "Operations Dashboard" },
            { key: "/inbound", icon: <ImportOutlined />, label: "Inbound" },
            { key: "/container-tracking", icon: <ImportOutlined />, label: "Container Tracking" },
            { key: "/inventory", icon: <DatabaseOutlined />, label: "Inventory" },
            { key: "/fba", icon: <TruckOutlined />, label: "FBA" },
            { key: "/outbound/dispatch", icon: <TruckOutlined />, label: "Outbound Dispatch" },
            { key: "/outbound/picking", icon: <TruckOutlined />, label: "Picking List" },
            { key: "/outbound/picking-history", icon: <HistoryOutlined />, label: "Picking History" },
            { key: "/outbound/bol", icon: <TruckOutlined />, label: "BOL" },
            { key: "/loads", icon: <TruckOutlined />, label: "Loads" },
            { key: "/work-orders", icon: <HistoryOutlined />, label: "Work Orders" },
            { key: "/trouble-shoot", icon: <HistoryOutlined />, label: "Trouble Shoot" },
            { key: "/documents", icon: <FileTextOutlined />, label: "Documents & POD" },
            {
              key: "/import-history",
              icon: <HistoryOutlined />,
              label: "Import History",
            },
            {
              key: "settings",
              icon: <SettingOutlined />,
              label: "Settings",
              disabled: true,
            },
          ]}
        />
        <Button
          className="sider-toggle"
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={() => setCollapsed(!collapsed)}
        >
          {!collapsed && "Collapse"}
        </Button>
      </Sider>
      <Layout>
        <Header className="topbar">
          <Typography.Text strong>Warehouse Operations</Typography.Text>
          <GlobalSearch />
          <NotificationCenter />
          <Button icon={<LogoutOutlined />} onClick={logout}>
            Sign Out
          </Button>
        </Header>
        <Content className={`content ${loc.pathname === "/outbound/dispatch" ? "content-workbench" : ""}`}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
