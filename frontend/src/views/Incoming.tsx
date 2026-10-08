import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { LineEditor, newEntry } from "@/components/line-editor";
import { api, istDay, paise, whole } from "@/lib/api";
import type { Product, Transaction, Post, OrderReview } from "@/lib/types";
import { OrderedGoods } from "@/components/ordered-goods";
import { OrderReceiving } from "@/components/order-receiving";
import { QuickPartDialog } from "@/components/quick-part";
import { UnbilledReceiving } from "@/components/unbilled-receiving";

function Receipt({
  transaction,
  post,
  role,
  openApprovals,
}: {
  role: "partner" | "staff";
  transaction: Transaction;
  post: Post;
  openApprovals: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      if (!confirmed)
        throw new Error("Confirm physical receipt before posting stock.");
      const lines = transaction.lines
        .filter((l) => (l.outstanding ?? 0) > 0)
        .map((l) => ({
          purchase_line_id: l.id,
          accepted: whole(String(data.get(`accepted-${l.id}`))),
          damaged: whole(String(data.get(`damaged-${l.id}`))),
          quarantined: whole(String(data.get(`quarantined-${l.id}`))),
        }))
        .filter((l) => l.accepted + l.damaged + l.quarantined > 0);
      if (!lines.length)
        throw new Error("Enter at least one physically received quantity.");
      setBusy(true);
      await post("/api/receipt-drafts", {
        purchase_id: transaction.id,
        confirmed,
        lines,
      });
      if (role === "partner") openApprovals();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title={String(transaction.data.supplier)}
      note={`${transaction.data.invoice_number} · ${transaction.data.invoice_date}`}
    >
      <form onSubmit={(e) => void save(e)}>
        <fieldset disabled={busy}>
          {transaction.lines
            .filter((l) => (l.outstanding ?? 0) > 0)
            .map((l) => (
              <div className="receipt-line" key={l.id}>
                <div>
                  <strong>{l.snapshot.name}</strong>
                  <small>
                    {l.outstanding} {l.snapshot.unit} outstanding · {l.received}{" "}
                    received of {l.quantity}
                  </small>
                </div>
                <Field label={`Accepted (${l.snapshot.unit})`}>
                  <Input
                    aria-label={`Accepted ${l.snapshot.sku}`}
                    name={`accepted-${l.id}`}
                    type="number"
                    min="0"
                    max={l.outstanding}
                    step="1"
                    defaultValue="0"
                    required
                  />
                </Field>
                <Field label={`Damaged (${l.snapshot.unit})`}>
                  <Input
                    aria-label={`Damaged ${l.snapshot.sku}`}
                    name={`damaged-${l.id}`}
                    type="number"
                    min="0"
                    max={l.outstanding}
                    step="1"
                    defaultValue="0"
                    required
                  />
                </Field>
                <Field label={`On hold (${l.snapshot.unit})`}>
                  <Input
                    aria-label={`Quarantined ${l.snapshot.sku}`}
                    name={`quarantined-${l.id}`}
                    type="number"
                    min="0"
                    max={l.outstanding}
                    step="1"
                    defaultValue="0"
                    required
                  />
                </Field>
              </div>
            ))}
          <Confirmation
            checked={confirmed}
            onChange={setConfirmed}
            label="I confirm these quantities physically arrived and were checked."
          />
          {error ? (
            <div role="alert" className="form-error">
              {error}
            </div>
          ) : null}
          <div className="actions">
            <span className="meta">
              {role === "staff"
                ? "A partner must review these counts."
                : "Next: review these counts and approve them. Stock is not available yet."}
            </span>
            <Button type="submit">
              {busy ? "Saving…" : "Save counts → review & approve"}
            </Button>
          </div>
        </fieldset>
      </form>
    </Panel>
  );
}
export default function Incoming({
  products,
  transactions,
  post,
  role,
  total,
  reviews = [],
  openApprovals,
  openAssistant,
}: {
  openAssistant: () => void;
  reviews?: OrderReview[];
  openApprovals: () => void;
  total: number;
  role: "partner" | "staff";
  products: Product[];
  transactions: Transaction[];
  post: Post;
}) {
  const [flow, setFlow] = useState<"orders" | "bill" | "no-bill">("orders");
  const [focusPurchase, setFocusPurchase] = useState<string | null>(null);
  const [addingPart, setAddingPart] = useState(false);
  const goods = products.filter((p) => p.kind === "goods");
  const [reviewing, setReviewing] = useState<OrderReview | null>(null);
  const [page, setPage] = useState(0);
  const [savedPage, setSavedPage] = useState<{
    items: Transaction[];
    total: number;
  } | null>(null);
  const [pageError, setPageError] = useState("");
  useEffect(() => {
    let active = true;
    setSavedPage(null);
    if (page)
      api<{ items: Transaction[]; total: number }>(
        `/api/incoming?offset=${page * 50}`,
      )
        .then((result) => {
          if (active) {
            setSavedPage(result);
            setPageError("");
          }
        })
        .catch((error) => {
          if (active) setPageError(error.message);
        });
    return () => {
      active = false;
    };
  }, [page, transactions]);
  const displayedTotal = savedPage?.total ?? total;
  const incoming = (page ? (savedPage?.items ?? []) : transactions).filter(
    (t) =>
      t.kind === "purchase" && t.lines.some((l) => (l.outstanding ?? 0) > 0),
  );
  const [entries, setEntries] = useState(() =>
    goods.length ? [newEntry(goods, false)] : [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      if (!entries.length) throw new Error("Add at least one goods line.");
      const payload = {
        supplier: data.get("supplier"),
        invoice_number: data.get("invoice"),
        invoice_date: data.get("date"),
        lines: entries.map((e) => ({
          product_id: e.productId,
          quantity: whole(e.quantity),
          unit: e.unit,
          cost_paise: paise(e.price),
        })),
      };
      setBusy(true);
      await post("/api/purchases", payload);
      form.reset();
      setEntries(goods.length ? [newEntry(goods, false)] : []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {role === "partner" ? (
        <Panel title="How are you adding stock?" note="Choose one option">
          <ol className="receiving-progress" aria-label="Receiving steps">
            <li>
              <strong>Confirm bill</strong>
              <span>Exact parts and units</span>
            </li>
            <li>
              <strong>Count</strong>
              <span>Accepted, damaged, on hold</span>
            </li>
            <li>
              <strong>Approve</strong>
              <span>Check saved counts</span>
            </li>
            <li>
              <strong>Ready to sell</strong>
              <span>Accepted stock available</span>
            </li>
          </ol>
          <div className="receiving-options">
            <Button
              variant={flow === "orders" ? "default" : "outline"}
              aria-pressed={flow === "orders"}
              onClick={() => {
                setFlow("orders");
                requestAnimationFrame(() =>
                  document
                    .getElementById("existing-orders")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" }),
                );
              }}
            >
              An existing order arrived
            </Button>
            <Button variant="outline" onClick={openAssistant}>
              Upload a supplier bill
            </Button>
            <Button
              variant={flow === "bill" ? "default" : "outline"}
              aria-pressed={flow === "bill"}
              onClick={() => setFlow("bill")}
            >
              Enter a bill myself
            </Button>
            <Button
              variant={flow === "no-bill" ? "default" : "outline"}
              aria-pressed={flow === "no-bill"}
              onClick={() => setFlow("no-bill")}
            >
              Goods arrived without a bill
            </Button>
          </div>
          <p>
            {flow === "orders"
              ? "Choose the next action on the order below. Check the parts, count them, then approve to make them available."
              : flow === "bill"
                ? "Save the supplier bill first. Count the delivery only after the goods reach the shop."
                : "Count only goods already at the shop. Use this option only when there is no bill or existing order."}
          </p>
        </Panel>
      ) : (
        <Panel
          title="Receive an existing order"
          note="Staff counts · partner approves"
        >
          <ol className="receiving-progress" aria-label="Receiving steps">
            <li>
              <strong>Confirm bill</strong>
              <span>Exact parts and units</span>
            </li>
            <li>
              <strong>Count</strong>
              <span>Accepted, damaged, on hold</span>
            </li>
            <li>
              <strong>Approve</strong>
              <span>Partner checks the counts</span>
            </li>
            <li>
              <strong>Ready to sell</strong>
              <span>Accepted stock available</span>
            </li>
          </ol>
          <p>
            Choose an order below, count what arrived, then ask a partner to
            approve. Staff cannot enter new bills or unbilled receipts here.
          </p>
        </Panel>
      )}
      {role === "staff" || flow === "orders" ? (
        <div id="existing-orders" className="existing-orders">
          {!reviews.length && !incoming.length ? (
            <Panel title="No orders waiting" note="Nothing to receive yet">
              <p>
                There are no saved orders waiting for delivery. Use “Upload a
                supplier bill” or “Enter a bill myself” first, or “Goods arrived
                without a bill” if the items are already at the shop.
              </p>
            </Panel>
          ) : null}
          <OrderedGoods
            reviews={reviews}
            onApprove={openApprovals}
            onReceive={(review) => {
              if (review.purchase_id) {
                setFocusPurchase(review.purchase_id);
                const target =
                  document.getElementById(
                    `delivery-count-${review.purchase_id}`,
                  ) ?? document.getElementById("delivery-counts");
                target?.scrollIntoView({ behavior: "smooth", block: "start" });
              } else setReviewing(review);
            }}
          />
          {reviewing ? (
            <OrderReceiving
              review={reviewing}
              products={products}
              post={post}
              close={() => setReviewing(null)}
            />
          ) : null}
          <div className="check-note">
            A bill records incoming purchases. Only a confirmed physical receipt
            makes accepted goods available for sale. Receipts use base units.
          </div>
        </div>
      ) : null}
      {role === "partner" && flow === "no-bill" ? (
        <UnbilledReceiving products={products} post={post} />
      ) : null}
      {role === "partner" && flow === "bill" ? (
        <Panel title="Record a supplier bill" note="Manual entry">
          <form onSubmit={(e) => void save(e)}>
            <fieldset disabled={busy}>
              <div className="grid">
                <Field label="Supplier name">
                  <Input
                    name="supplier"
                    required
                    maxLength={200}
                    placeholder="Exact supplier identity"
                  />
                </Field>
                <Field label="Invoice number">
                  <Input
                    name="invoice"
                    required
                    maxLength={200}
                    placeholder="As printed on the bill"
                  />
                </Field>
                <Field label="Invoice date">
                  <Input
                    name="date"
                    type="date"
                    required
                    defaultValue={istDay()}
                  />
                </Field>
              </div>
              {!goods.length ? (
                <p className="check-note">
                  No parts yet. Choose Add item to create your first part here.
                </p>
              ) : null}
              <LineEditor
                products={goods}
                entries={entries}
                setEntries={setEntries}
                disabled={busy}
                onNewPart={() => setAddingPart(true)}
              />
              {error ? (
                <div className="form-error" role="alert">
                  {error}
                </div>
              ) : null}
              <div className="actions">
                <span className="meta">
                  Creates incoming stock. Does not confirm delivery.
                </span>
                <Button type="submit" disabled={!goods.length}>
                  {busy ? "Saving…" : "Save incoming bill"}
                </Button>
              </div>
            </fieldset>
          </form>
        </Panel>
      ) : null}
      {role === "staff" || flow !== "no-bill" ? (
        <>
          <div className="section-top" id="delivery-counts">
            <h2>Count delivery</h2>
            <span className="meta">
              {displayedTotal} bills with outstanding items · page {page + 1}
            </span>
          </div>
          {pageError ? (
            <p role="alert" className="form-error">
              {pageError}
            </p>
          ) : null}
          <div className="actions">
            <Button
              variant="outline"
              disabled={!page}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous bills
            </Button>
            <Button
              variant="outline"
              disabled={(page + 1) * 50 >= displayedTotal}
              onClick={() => setPage((p) => p + 1)}
            >
              Next bills
            </Button>
          </div>
          {page && !savedPage && !pageError ? <p>Loading bills…</p> : null}
          {incoming.map((tx) => (
            <div
              key={`${tx.id}:${tx.lines.map((l) => l.outstanding).join(",")}`}
              id={`delivery-count-${tx.id}`}
              className={focusPurchase === tx.id ? "receipt-focus" : undefined}
            >
              <Receipt
                transaction={tx}
                role={role}
                post={post}
                openApprovals={openApprovals}
              />
            </div>
          ))}
          {!incoming.length && (!page || savedPage) ? (
            <div className="panel empty">
              No outstanding stock on recorded bills.
            </div>
          ) : null}
        </>
      ) : null}
      {addingPart ? (
        <QuickPartDialog
          post={post}
          close={() => setAddingPart(false)}
          onSaved={(part) =>
            setEntries((old) => [
              ...old,
              {
                id: crypto.randomUUID(),
                productId: part.id,
                unit: part.unit,
                quantity: "1",
                price: part.cost,
              },
            ])
          }
        />
      ) : null}
    </>
  );
}
