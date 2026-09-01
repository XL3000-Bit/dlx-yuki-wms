import { Card, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";

export const COMPANY_ITEMS: Record<string, { title: string; group: string; note: string; alias?: string }> = {
  "user-management": { title: "User Management", group: "My Company", note: "Yuki currently uses login roles ADMIN / OPERATOR. Full user admin is not built yet." },
  "company-profile": { title: "Company Profile", group: "My Company", note: "Company name, warehouse identity and contact profile will live here." },
  "email-setting": { title: "Email Setting", group: "My Company", note: "Outbound notification mail is not configured in this build." },
  "access-control": { title: "Access Control", group: "My Company", note: "Page access follows the signed-in role. Granular ACL is not enabled." },
  "trade-party": { title: "Trade Party", group: "My Company", note: "Maps to Yuki customers / shippers used on inbound and outbound." },
  "area-group": { title: "Area Group", group: "My Company", note: "Regional grouping for warehouses. Not a live table yet." },
  "warehouse-point-group": { title: "Warehouse Point Group", group: "My Company", note: "Related to 仓点 values in West Coast 4.0. Confirm semantics before importing." },
  zone: { title: "Zone", group: "My Company", note: "Warehouse zone / location grouping. Inventory locations exist on lots." },
  "service-setting": { title: "Service Setting", group: "My Company", note: "Service types for inbound, FBA and outbound." },
  "commission-setting": { title: "Commission Setting", group: "My Company", note: "Not used by current warehouse operations." },
  "team-setting": { title: "Team Setting", group: "My Company", note: "Loading team / operator roster placeholder." },
  "company-code": { title: "Company Code", group: "My Company", note: "Legal entity / bill-to codes." },
  "preference-setting": { title: "Preference Setting", group: "My Company", note: "UI density, timezone America/Los_Angeles, default warehouse." },
  "ocean-carrier": { title: "Ocean Carrier", group: "Entities", note: "Maps to Yuki carrier master used on container tracking and outbound." },
  terminals: { title: "Terminals", group: "Entities", note: "Port / rail terminal list. Not a live table yet." },
  "shipping-modes": { title: "Shipping Modes", group: "Entities", note: "FBA, transfer, pickup and other outbound types already exist on OB." },
  "force-majeure": { title: "Force Majeure Events", group: "Entities", note: "Exception catalog can later feed Trouble Shoot." },
  "gl-codes": { title: "General Ledger Codes", group: "Controller Tools", note: "Accounting is out of current Yuki WMS scope." },
  "billing-codes": { title: "Billing Codes", group: "Controller Tools", note: "Warehouse billing codes are not enabled." },
  "bank-account": { title: "Bank Account", group: "Controller Tools", note: "Not part of warehouse operations." },
  "account-block": { title: "Account Block", group: "Controller Tools", note: "Not part of warehouse operations." },
  "income-statement": { title: "Income Statement", group: "Controller Tools", note: "Not part of warehouse operations." },
  "balance-sheet": { title: "Balance Sheet", group: "Controller Tools", note: "Not part of warehouse operations." },
};

export function CompanySettingsPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
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
        <Typography.Text type="secondary">Menu entry is available. Live master-data editing can be added after the table is confirmed.</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <a onClick={() => nav(-1)}>Back</a>
        </div>
      </Card>
    </div>
  );
}
