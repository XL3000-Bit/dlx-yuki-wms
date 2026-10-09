import { Card, Tag, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { UserManagementPage } from "./UserManagementPage";
import { CompanyProfilePage } from "./CompanyProfilePage";
import { SETTINGS_ITEMS } from "./companyCatalog";

export function CompanySettingsPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  if (slug === "users" || slug === "user-management") return <div className="page"><UserManagementPage /></div>;
  if (slug === "company-profile") return <div className="page"><CompanyProfilePage /></div>;
  const item = SETTINGS_ITEMS[slug];
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>{item?.title || "System Settings"}</Typography.Title>
          <Typography.Text type="secondary">{item?.group || "Settings"}</Typography.Text>
        </div>
        <Tag color="orange">Coming Soon</Tag>
      </div>
      <Card>
        <p>{item?.note || "This setting is not registered."}</p>
        <Typography.Text type="secondary">
          Live in PHASE 12.1: Company Profile and User Management. Master data editors start in 12.2.
        </Typography.Text>
        <div style={{ marginTop: 16 }}>
          <a onClick={() => nav(-1)}>Back</a>
        </div>
      </Card>
    </div>
  );
}
