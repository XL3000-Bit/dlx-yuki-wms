import { SettingOutlined } from "@ant-design/icons";
import { Button, Dropdown } from "antd";
import { useNavigate } from "react-router-dom";

const groups = [
  {
    title: "My Company",
    items: [
      ["User Management", "/company/user-management"],
      ["Company Profile", "/company/company-profile"],
      ["Email Setting", "/company/email-setting"],
      ["Access Control", "/company/access-control"],
      ["Trade Party", "/company/trade-party"],
      ["Area Group", "/company/area-group"],
      ["Warehouse Point Group", "/company/warehouse-point-group"],
      ["Zone", "/company/zone"],
      ["Service Setting", "/company/service-setting"],
      ["Commission Setting", "/company/commission-setting"],
      ["Team Setting", "/company/team-setting"],
      ["Company Code", "/company/company-code"],
      ["Preference Setting", "/company/preference-setting"],
    ],
  },
  {
    title: "Entities",
    items: [
      ["Ocean Carrier", "/company/ocean-carrier"],
      ["Terminals", "/company/terminals"],
      ["Shipping Modes", "/company/shipping-modes"],
      ["Force Majeure Events", "/company/force-majeure"],
    ],
  },
  {
    title: "Controller Tools",
    items: [
      ["General Ledger Codes", "/company/gl-codes"],
      ["Billing Codes", "/company/billing-codes"],
      ["Bank Account", "/company/bank-account"],
      ["Account Block", "/company/account-block"],
      ["Income Statement", "/company/income-statement"],
      ["Balance Sheet", "/company/balance-sheet"],
    ],
  },
];

export function CompanyMenu() {
  const nav = useNavigate();
  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      popupRender={() => (
        <div className="company-mega">
          {groups.map((group) => (
            <section key={group.title}>
              <h4>{group.title}</h4>
              {group.items.map(([label, path]) => (
                <button key={path} type="button" onClick={() => nav(path)}>{label}</button>
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
