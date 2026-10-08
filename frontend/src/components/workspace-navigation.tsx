import { useState } from "react";
import { Menu, ChevronRight } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { navigation, views, type View } from "@/lib/navigation";
import type { User } from "@/lib/types";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark kcd-monogram" aria-hidden="true">
        KCD
      </span>
      <span>
        Kakinada<small>Car Decors</small>
      </span>
    </div>
  );
}

export function WorkspaceNavigation({
  user,
  view,
  onChange,
}: {
  user: User;
  view: View;
  onChange: (view: View) => void;
}) {
  const [open, setOpen] = useState(false);
  const items = navigation.filter(
    (item) => user.role === "partner" || item.group === "Daily work",
  );
  const label = (key: View) =>
    key === "approvals" && user.role === "staff"
      ? "My count drafts"
      : views[key][0];
  const select = (next: View) => {
    onChange(next);
    setOpen(false);
  };
  const links = (
    <nav aria-label="Main navigation">
      {["Daily work", "Management"].map((group) => {
        const grouped = items.filter((item) => item.group === group);
        return grouped.length ? (
          <div className="nav-group" key={group}>
            <div className="workspace-label">{group}</div>
            {grouped.map(({ key, icon: Icon }) => (
              <Button
                key={key}
                variant="ghost"
                className={`nav ${view === key ? "active" : ""}`}
                aria-current={view === key ? "page" : undefined}
                onClick={() => select(key)}
              >
                <Icon aria-hidden="true" />
                <span>{label(key)}</span>
                {view === key ? (
                  <ChevronRight className="nav-chevron" aria-hidden="true" />
                ) : null}
              </Button>
            ))}
          </div>
        ) : null;
      })}
    </nav>
  );
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <Brand />
        {links}
        <div className="sidebar-note">
          <span className="workspace-avatar">
            {user.username.charAt(0).toUpperCase()}
          </span>
          <div>
            <strong>{user.username}</strong>
            <small>
              {user.role === "partner"
                ? "Partner workspace"
                : "Staff workspace"}
            </small>
          </div>
        </div>
      </aside>
      <div className="mobile-brand">
        <Brand />
        <Button
          variant="outline"
          size="icon"
          aria-label="Open navigation"
          onClick={() => setOpen(true)}
        >
          <Menu aria-hidden="true" />
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="navigation-dialog">
          <DialogHeader>
            <DialogTitle>Shop workspace</DialogTitle>
            <DialogDescription>Choose what you want to do.</DialogDescription>
          </DialogHeader>
          {links}
        </DialogContent>
      </Dialog>
      <nav className="mobile-dock" aria-label="Quick navigation">
        {items
          .filter((item) =>
            ["stock", "incoming", "sale", "approvals"].includes(item.key),
          )
          .map(({ key, icon: Icon }) => (
            <Button
              key={key}
              variant="ghost"
              className={view === key ? "active" : ""}
              aria-label={label(key)}
              aria-current={view === key ? "page" : undefined}
              onClick={() => select(key)}
            >
              <Icon aria-hidden="true" />
              <span>
                {key === "stock"
                  ? "Inventory"
                  : key === "incoming"
                    ? "Receive"
                    : key === "sale"
                      ? "Sale"
                      : user.role === "partner"
                        ? "Approvals"
                        : "My drafts"}
              </span>
            </Button>
          ))}
      </nav>
    </>
  );
}
