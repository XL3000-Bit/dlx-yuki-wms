import { SettingOutlined } from "@ant-design/icons";
import { Button, Dropdown } from "antd";
import { useNavigate } from "react-router-dom";
import { useCurrentUser } from "../hooks/usePermissions";

const groups = [
  {
    title: "My Company",
    items: [
      { label: "Import History", path: "/import-history" },
      { label: "Documents & POD", path: "/documents" },
      { label: "Data Upload", path: "/admin/data-upload", admin: true },
    ],
  },
  {
    title: "Entities",
    items: [
      { label: "Container Tracking", path: "/container-tracking" },
      { label: "Inventory", path: "/inventory" },
      { label: "FBA Shipments", path: "/fba" },
      { label: "Loads", path: "/loads" },
    ],
  },
  {
    title: "Controller Tools",
    items: [
      { label: "Operations Dashboard", path: "/dashboard" },
      { label: "Work Orders", path: "/work-orders" },
      { label: "Trouble Shoot", path: "/trouble-shoot" },
      { label: "Outbound Dispatch", path: "/outbound/dispatch" },
    ],
  },
];

export function CompanyMenu() {
  const nav = useNavigate();
  const me = useCurrentUser();
  const isAdmin = me.data?.role === "ADMIN";
  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      popupRender={() => (
        <div className="company-mega">
          {groups.map((group) => (
            <section key={group.title}>
              <h4>{group.title}</h4>
              {group.items.filter((item) => !item.admin || isAdmin).map((item) => (
                <button key={item.path} type="button" onClick={() => nav(item.path)}>
                  {item.label}
                </button>
              ))}
            </section>
          ))}
        </div>
      )}
    >
      <Button className="topbar-icon" shape="circle" icon={<SettingOutlined />} aria-label="Company menu" />
    </Dropdown>
  );
}
