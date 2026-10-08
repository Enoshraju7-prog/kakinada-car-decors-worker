import { useEffect, useState } from "react";
import { api, time } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Bell } from "@/lib/icons";
interface Alert {
  id: string;
  event: string;
  kind?: string;
  actor: string;
  source_id: string;
  created_at: string;
}
const labels: Record<string, string> = {
  sale: "Sale recorded",
  reversal: "Record reversed",
  return: "Return recorded",
  adjustment: "Stock corrected",
  prices: "Item prices changed",
  unbilled_receipt: "Goods received without a bill",
};
export function PartnerAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true;
    const load = () =>
      void api<Alert[]>("/api/partner-alerts")
        .then((a) => {
          if (active) {
            setAlerts(a);
            setError("");
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    load();
    const interval = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);
  return (
    <>
      <Button
        variant="ghost"
        aria-label={`Partner alerts, ${alerts.length} recent events`}
        onClick={() => setOpen(true)}
      >
        <Bell aria-hidden="true" />
        <span className="button-label">Alerts</span>
        {alerts.length ? (
          <span className="alert-count">{alerts.length}</span>
        ) : null}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Partner alerts</DialogTitle>
            <DialogDescription>
              Sales, corrections and price changes. Shared with every partner;
              refreshed every 30 seconds while signed in.
            </DialogDescription>
          </DialogHeader>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : !alerts.length ? (
            <p>No recent activity.</p>
          ) : (
            <div className="partner-alert-list">
              {alerts.map((a) => (
                <article key={a.id}>
                  <strong>
                    {labels[a.kind ?? a.event] ??
                      labels[a.event] ??
                      "Activity recorded"}
                  </strong>
                  <p>
                    {a.actor} · {time(a.created_at)}
                  </p>
                  <small>Reference: {a.source_id}</small>
                </article>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
