import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { LineEditor, newEntry } from "@/components/line-editor";
import { money, paise, whole } from "@/lib/api";
import type { Product, Post } from "@/lib/types";
import { CustomerDetails, type Customer } from "@/components/customer-details";
import { SaleReceipt } from "@/components/sale-receipt";

export default function Sale({
  products,
  post,
  partner,
}: {
  products: Product[];
  post: Post;
  partner: boolean;
}) {
  const [entries, setEntries] = useState(() =>
    products.length ? [newEntry(products, true)] : [],
  );
  const [payment, setPayment] = useState("cash");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedSaleId, setSavedSaleId] = useState<string | null>(null);
  function payload() {
    if (!entries.length)
      throw new Error("Add at least one product or service line.");
    if (customer && (!customer.name.trim() || !customer.phone.trim()))
      throw new Error(
        "Enter the customer name and mobile number, or choose Walk-in.",
      );
    return {
      payment,
      ...(customer ? { customer } : {}),
      lines: entries.map((e) => ({
        product_id: e.productId,
        quantity: whole(e.quantity),
        price_paise: paise(e.price),
      })),
    };
  }
  let total: string;
  try {
    total = money(
      entries.reduce((n, e) => n + whole(e.quantity) * paise(e.price), 0),
    );
  } catch {
    total = "Check amounts";
  }
  function prepare(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      payload();
      if (!confirmed)
        throw new Error("Confirm the goods were checked and handed over.");
      setReview(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const saved = await post("/api/sales", payload());
      setSavedSaleId(saved.id);
      setReview(false);
      setEntries(products.length ? [newEntry(products, true)] : []);
      setConfirmed(false);
      setCustomer(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {savedSaleId ? (
        <Panel title="Sale saved" note="Your bill is ready">
          <SaleReceipt saleId={savedSaleId} />
        </Panel>
      ) : null}
      <div className="check-note">
        Credit sales remove handed-over stock too. Fitting charges never reduce
        stock.
      </div>
      <Panel title="Counter sale" note="INR · stock record">
        <form onSubmit={prepare}>
          <fieldset disabled={busy}>
            <LineEditor
              products={products}
              entries={entries}
              setEntries={setEntries}
              sale
              disabled={busy}
            />
            {partner && (
              <CustomerDetails
                key={customer === null ? "walk-in" : "customer"}
                value={customer}
                onChange={setCustomer}
                disabled={busy}
              />
            )}
            <div className="grid two form-lines">
              <Field label="Payment method">
                <NativeSelect
                  aria-label="Payment method"
                  value={payment}
                  onChange={(e) => setPayment(e.target.value)}
                >
                  {["cash", "upi", "card", "credit"].map((p) => (
                    <NativeSelectOption key={p} value={p}>
                      {p.toUpperCase()} · {p === "credit" ? "unpaid" : "paid"}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <div>
                <span className="meta">Recorded total</span>
                <div className="counter-total">{total}</div>
              </div>
            </div>
            <Confirmation
              label="I checked the variants, quantities and prices, and handed over the goods."
              checked={confirmed}
              onChange={setConfirmed}
            />
            {error ? (
              <div role="alert" className="form-error">
                {error}
              </div>
            ) : null}
            <div className="actions">
              <span className="meta">
                Save the sale to update the remaining stock.
              </span>
              <Button type="submit" disabled={!products.length}>
                Review sale
              </Button>
            </div>
            <div className="price-note">
              Amounts are recorded as entered. Tax invoices and discounts are
              not configured.
            </div>
          </fieldset>
        </form>
      </Panel>
      <Dialog
        open={review}
        onOpenChange={(open) => {
          if (!busy) setReview(open);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm counter sale</DialogTitle>
            <DialogDescription>
              {entries.length} lines · {total} ·{" "}
              {payment === "credit" ? "credit / unpaid" : payment + " / paid"}.
              Goods stock will decrease when this sale is saved.
            </DialogDescription>
          </DialogHeader>
          {entries.map((e) => (
            <div key={e.id} className="text-sm">
              {products.find((p) => p.id === e.productId)?.name} · {e.quantity}
            </div>
          ))}
          {error ? (
            <div role="alert" className="form-error">
              {error}
            </div>
          ) : null}
          <DialogFooter>
            <p className="text-sm">
              {customer
                ? `Customer: ${customer.name} · ${customer.phone}`
                : "Walk-in customer"}
            </p>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setReview(false)}
            >
              Back to sale
            </Button>
            <Button disabled={busy} onClick={() => void save()}>
              {busy ? "Saving…" : "Confirm sale"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
