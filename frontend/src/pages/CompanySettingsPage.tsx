import { Card, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { UserManagementPage } from "./UserManagementPage";
import { CompanyProfilePage } from "./CompanyProfilePage";
import { COMPANY_ITEMS } from "./companyCatalog";

export function CompanySettingsPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  if (slug === "user-management") return <div className="page"><UserManagementPage /></div>;
  if (slug === "company-profile") return <div className="page"><CompanyProfilePage /></div>;
  const item = COMPANY_ITEMS[slug];
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>{item?.title || "Company setting"}</Typography.Title>
          <Typography.Text type="secondary">{item?.group || "Settings"}</Typography.Text>
        </div>
      </div>
      <Card>
        <p>{item?.note || "This setting is not registered."}</p>
        <Typography.Text type="secondary">Live pages so far: User Management, Company Profile.</Typography.Text>
        <div style={{ marginTop: 16 }}><a onClick={() => nav(-1)}>Back</a></div>
      </Card>
    </div>
  );
}
