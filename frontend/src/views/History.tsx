import { useState, type FormEvent } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shop-form";
import { money, time, whole } from "@/lib/api";
import type { Transaction, Post } from "@/lib/types";
import { SaleCustomer } from "@/components/customer-details";
import { SaleReceipt } from "@/components/sale-receipt";

function ReturnForm({
  transaction,
  post,
}: {
  transaction: Transaction;
  post: Post;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const eligible = transaction.lines.filter(
    (l) => l.snapshot.kind === "goods" && (l.returned ?? 0) < l.quantity,
  );
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const lines = eligible
        .map((l) => ({
          sale_line_id: l.id,
          quantity: whole(String(data.get(`quantity-${l.id}`))),
          damaged: whole(String(data.get(`damaged-${l.id}`))),
        }))
        .filter((l) => l.quantity > 0 || l.damaged > 0);
      if (!lines.length) throw new Error("Enter a returned goods quantity.");
      setBusy(true);
      await post("/api/returns", {
        sale_id: transaction.id,
        reason: data.get("reason"),
        lines,
      });
      form.reset();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!eligible.length) return null;
  return (
    <form onSubmit={(e) => void save(e)}>
      <fieldset disabled={busy}>
        <h3>Record a goods return</h3>
        <p>Refund payment is a separate settlement.</p>
        {eligible.map((l) => (
          <div key={l.id} className="return-line">
            <strong>
              {l.snapshot.name}
              <small className="meta">
                {" "}
                · {l.quantity - (l.returned ?? 0)} {l.snapshot.unit} returnable
              </small>
            </strong>
            <Field label="Total returned">
              <Input
                aria-label={`Total returned ${l.snapshot.sku}`}
                name={`quantity-${l.id}`}
                type="number"
                min="0"
                max={l.quantity - (l.returned ?? 0)}
                step="1"
                defaultValue="0"
                required
              />
            </Field>
            <Field label="Of these, damaged">
              <Input
                aria-label={`Damaged return ${l.snapshot.sku}`}
                name={`damaged-${l.id}`}
                type="number"
                min="0"
                max={l.quantity - (l.returned ?? 0)}
                step="1"
                defaultValue="0"
                required
              />
            </Field>
          </div>
        ))}
        <Field label="Reason">
          <Input
            name="reason"
            required
            maxLength={200}
            placeholder="Reason and condition of returned goods"
          />
        </Field>
        {error ? (
          <div className="form-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="actions">
          <Button type="submit" variant="outline">
            {busy ? "Saving…" : "Confirm return"}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
export default function History({
  transactions,
  movementCount,
  post,
  partner,
}: {
  transactions: Transaction[];
  movementCount: number;
  partner: boolean;
  post: Post;
}) {
  return (
    <Card className="panel gap-0 py-0">
      <CardHeader className="panel-head">
        <CardTitle>Posted transactions</CardTitle>
        <small>
          {transactions.length} source records · {movementCount} stock movements
        </small>
      </CardHeader>
      {transactions.map((tx) => (
        <details key={tx.id}>
          <summary>
            <Badge className="badge">{tx.kind}</Badge>{" "}
            {tx.kind === "purchase"
              ? `${tx.data.invoice_number} · ${tx.data.supplier}`
              : tx.kind === "sale"
                ? `${money(tx.total_paise)} · ${tx.data.payment_status}`
                : tx.kind === "return"
                  ? tx.data.reason
                  : tx.kind === "receipt"
                    ? "Physical receipt confirmed"
                    : tx.data.reason}
            <small>{time(tx.created_at)}</small>
          </summary>
          <div className="history-detail">
            Reference: <code>{tx.id}</code>
            <br />
            Recorded by {tx.actor}
            {tx.kind === "sale" && partner ? (
              <SaleCustomer saleId={tx.id} />
            ) : null}
            {tx.reversed ? " · REVERSED" : null}
            {tx.kind === "sale" ? <SaleReceipt saleId={tx.id} /> : null}
            {tx.parent_id ? (
              <>
                <br />
                Linked source: <code>{tx.parent_id}</code>
              </>
            ) : null}
            {tx.lines.map((l) => (
              <div key={l.id}>
                {l.snapshot.name} · {l.quantity} {l.snapshot.unit}
                {l.damaged ? ` · ${l.damaged} damaged` : ""}
                {tx.kind === "sale" ? ` · ${l.returned} returned` : ""}
              </div>
            ))}
            {tx.movements.length ? (
              tx.movements.map((m) => (
                <div key={m.id}>
                  Stock movement: quarantine {m.quarantined_delta} · available{" "}
                  {m.available_delta >= 0 ? "+" : ""}
                  {m.available_delta} / damaged +{m.damaged_delta} · {m.id}
                </div>
              ))
            ) : (
              <p>No stock movements (incoming bill or service-only sale).</p>
            )}
          </div>
          {partner && !tx.reversed && tx.kind !== "reversal" ? (
            <Reversal transaction={tx} post={post} />
          ) : null}
          {tx.kind === "sale" && partner && !tx.reversed ? (
            <ReturnForm
              key={tx.lines.map((l) => l.returned).join(",")}
              transaction={tx}
              post={post}
            />
          ) : null}
        </details>
      ))}
      {!transactions.length ? (
        <div className="empty">The first posted source will appear here.</div>
      ) : null}
    </Card>
  );
}

function Reversal({
  transaction,
  post,
}: {
  transaction: Transaction;
  post: Post;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await post("/api/reversals", {
        transaction_id: transaction.id,
        reason: data.get("reason"),
        evidence: data.get("evidence"),
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>Reverse this source</summary>
      <form onSubmit={(e) => void save(e)}>
        <fieldset disabled={busy}>
          <p>
            Allowed only when no linked dependants or later stock changes exist.
            Otherwise review a physical count.
          </p>
          <Field label="Correction reason">
            <Input name="reason" required maxLength={200} />
          </Field>
          <Field label="Evidence">
            <Input name="evidence" required maxLength={200} />
          </Field>
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
          <Button type="submit" variant="outline">
            {busy ? "Saving…" : "Confirm reversal"}
          </Button>
        </fieldset>
      </form>
    </details>
  );
}
