import { SettingOutlined } from "@ant-design/icons";
import { Button, Drawer, Dropdown, Grid } from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCurrentUser } from "../hooks/usePermissions";
import { SETTINGS_GROUPS, type SettingsItem } from "../pages/companyCatalog";

function MenuPanel({
  itemsVisible,
  onPick,
}: {
  itemsVisible: typeof SETTINGS_GROUPS;
  onPick: (item: SettingsItem) => void;
}) {
  return (
    <div className="company-mega">
      {itemsVisible.map((group) => (
        <section key={group.title}>
          <h4>{group.title}</h4>
          {group.items.map((item) => (
            <button
              key={item.slug}
              type="button"
              className={item.status === "soon" ? "is-soon" : "is-live"}
              onClick={() => onPick(item)}
            >
              <span>{item.title}</span>
              {item.status === "soon" && <em>Coming Soon</em>}
            </button>
          ))}
        </section>
      ))}
    </div>
  );
}

export function CompanyMenu() {
  const nav = useNavigate();
  const screens = Grid.useBreakpoint();
  const compact = !screens.md;
  const [open, setOpen] = useState(false);
  const me = useCurrentUser();
  const role = me.data?.role;
  const hidden = role === "VIEWER";
  const isAdmin = role === "ADMIN";

  const itemsVisible = useMemo(
    () =>
      SETTINGS_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter((item) => !item.adminOnly || isAdmin),
      })),
    [isAdmin],
  );

  const pick = (item: SettingsItem) => {
    setOpen(false);
    nav(item.path);
  };

  if (hidden) return null;

  const trigger = (
    <Button className="topbar-icon" shape="circle" icon={<SettingOutlined />} aria-label="System Settings" />
  );

  if (compact) {
    return (
      <>
        <span onClick={() => setOpen(true)}>{trigger}</span>
        <Drawer title="System Settings" open={open} onClose={() => setOpen(false)} width={360}>
          <MenuPanel itemsVisible={itemsVisible} onPick={pick} />
        </Drawer>
      </>
    );
  }

  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      popupRender={() => <MenuPanel itemsVisible={itemsVisible} onPick={pick} />}
    >
      {trigger}
    </Dropdown>
  );
}
