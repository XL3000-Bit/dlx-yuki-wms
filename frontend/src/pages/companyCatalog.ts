export type SettingsStatus = "live" | "soon";
export type SettingsItem = {
  slug: string;
  title: string;
  group: string;
  note: string;
  status: SettingsStatus;
  adminOnly?: boolean;
  path: string;
};

export const SETTINGS_GROUPS: { title: string; items: SettingsItem[] }[] = [
  {
    title: "Company & Access",
    items: [
      { slug: "company-profile", title: "Company Profile", group: "Company & Access", note: "Company name, brand and default warehouse.", status: "live", path: "/settings/company-profile" },
      { slug: "users", title: "User Management", group: "Company & Access", note: "Create users, roles and active flag.", status: "live", adminOnly: true, path: "/settings/users" },
      { slug: "access", title: "Access Control", group: "Company & Access", note: "Role and warehouse/customer scope UI is PHASE 12.3.", status: "soon", adminOnly: true, path: "/settings/access" },
      { slug: "team-setting", title: "Team Setting", group: "Company & Access", note: "Reuse user roster. No separate team table.", status: "soon", path: "/settings/team-setting" },
      { slug: "email-setting", title: "Email Setting", group: "Company & Access", note: "No mail backend yet.", status: "soon", adminOnly: true, path: "/settings/email-setting" },
      { slug: "company-code", title: "Company Code", group: "Company & Access", note: "Fold into Company Profile later.", status: "soon", path: "/settings/company-code" },
      { slug: "preference-setting", title: "Preference Setting", group: "Company & Access", note: "Timezone already America/Los_Angeles.", status: "soon", path: "/settings/preference-setting" },
      { slug: "audit-log", title: "Audit Log", group: "Company & Access", note: "audit_logs table exists. Page is PHASE 12.4.", status: "soon", adminOnly: true, path: "/settings/audit-log" },
    ],
  },
  {
    title: "Master Data",
    items: [
      { slug: "customers", title: "Trade Party", group: "Master Data", note: "Reuses customers. Admin page is PHASE 12.2.", status: "soon", path: "/settings/customers" },
      { slug: "areas", title: "Area Group", group: "Master Data", note: "Reuses warehouse_areas.", status: "soon", path: "/settings/areas" },
      { slug: "warehouse-point-group", title: "Warehouse Point Group", group: "Master Data", note: "West Coast 仓点 mapping. Do not clone warehouses.", status: "soon", path: "/settings/warehouse-point-group" },
      { slug: "warehouses", title: "Warehouse", group: "Master Data", note: "Reuses warehouses.", status: "soon", path: "/settings/warehouses" },
      { slug: "zone", title: "Zone", group: "Master Data", note: "Same as warehouse_areas until a rule splits them.", status: "soon", path: "/settings/zone" },
      { slug: "locations", title: "Location", group: "Master Data", note: "Reuses warehouse_locations.", status: "soon", path: "/settings/locations" },
      { slug: "service-setting", title: "Service Setting", group: "Master Data", note: "Reuse outbound OBType enum.", status: "soon", path: "/settings/service-setting" },
      { slug: "carriers", title: "Ocean Carrier", group: "Master Data", note: "Reuses carriers.", status: "soon", path: "/settings/carriers" },
      { slug: "terminals", title: "Terminals", group: "Master Data", note: "Not required until container tracking needs a terminal FK.", status: "soon", path: "/settings/terminals" },
      { slug: "shipping-modes", title: "Shipping Modes", group: "Master Data", note: "Reuse outbound types.", status: "soon", path: "/settings/shipping-modes" },
      { slug: "fc-addresses", title: "FC Address Book", group: "Master Data", note: "Reuses amazon_fc_addresses.", status: "soon", path: "/settings/fc-addresses" },
      { slug: "exception-reasons", title: "Exception Reasons", group: "Master Data", note: "Reuse ExceptionType on Trouble Shoot.", status: "soon", path: "/settings/exception-reasons" },
      { slug: "force-majeure", title: "Force Majeure Events", group: "Master Data", note: "Deferred.", status: "soon", path: "/settings/force-majeure" },
    ],
  },
  {
    title: "Control & Finance",
    items: [
      { slug: "documents", title: "Document Templates", group: "Control & Finance", note: "Current default is the live BOL generator.", status: "soon", path: "/settings/documents" },
      { slug: "numbering", title: "Numbering Rules", group: "Control & Finance", note: "Numbers are allocated in services today.", status: "soon", adminOnly: true, path: "/settings/numbering" },
      { slug: "workflow", title: "Status & Workflow", group: "Control & Finance", note: "Status enums already live on operational docs.", status: "soon", path: "/settings/workflow" },
      { slug: "billing-codes", title: "Billing Codes", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/billing-codes" },
      { slug: "gl-codes", title: "General Ledger Codes", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/gl-codes" },
      { slug: "account-block", title: "Account Block", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/account-block" },
      { slug: "bank-account", title: "Bank Account", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/bank-account" },
      { slug: "commission-setting", title: "Commission Setting", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/commission-setting" },
      { slug: "income-statement", title: "Income Statement", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/income-statement" },
      { slug: "balance-sheet", title: "Balance Sheet", group: "Control & Finance", note: "Out of WMS scope.", status: "soon", adminOnly: true, path: "/settings/balance-sheet" },
    ],
  },
];

export const SETTINGS_ITEMS = Object.fromEntries(
  SETTINGS_GROUPS.flatMap((group) => group.items.map((item) => [item.slug, item])),
) as Record<string, SettingsItem>;

export const COMPANY_ITEMS = SETTINGS_ITEMS;
