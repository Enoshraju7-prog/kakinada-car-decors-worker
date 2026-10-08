import { QuickPartDialog } from "@/components/quick-part";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Field, Confirmation } from "@/components/shop-form";
import { money, paise, whole } from "@/lib/api";
import type { OrderReview, Product, Post } from "@/lib/types";

export function OrderReceiving({
  review,
  products,
  post,
  close,
}: {
  review: OrderReview;
  products: Product[];
  post: Post;
  close: () => void;
}) {
  const [rows, setRows] = useState(() =>
    review.payload.lines.map((line, source_index) => ({
      key: crypto.randomUUID(),
      source_index,
      product_id: "",
      unit: "",
      quantity: String(line.quantity_candidate ?? ""),
      rate: line.quantity_candidate
        ? String(line.amount_paise / 100 / line.quantity_candidate)
        : "",
    })),
  );
  const [newPartRow, setNewPartRow] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const goods = products.filter((p) => p.kind === "goods");
  const update = (key: string, field: string, value: string) => {
    setConfirmed(false);
    setRows((old) =>
      old.map((row) => (row.key === key ? { ...row, [field]: value } : row)),
    );
  };
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      if (!confirmed)
        throw new Error(
          "Confirm the invoice details and exact item mappings first.",
        );
      for (const row of rows) {
        if (!row.product_id)
          throw new Error("Choose an exact part for every bill line.");
        if (!row.unit)
          throw new Error(
            "Confirm the supplier unit under Unit and buying rate.",
          );
        if (!row.quantity || !row.rate)
          throw new Error("Enter quantity and buying rate for every line.");
      }
      setBusy(true);
      await post("/api/purchases", {
        order_review_id: review.id,
        review_confirmed: true,
        supplier: review.payload.supplier,
        invoice_number: review.payload.invoice_number,
        invoice_date: new FormData(event.currentTarget).get("invoice_date"),
        lines: rows.map((row) => ({
          source_index: row.source_index,
          product_id: row.product_id,
          quantity: whole(row.quantity),
          unit: row.unit,
          cost_paise: paise(row.rate),
        })),
      });
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open && !busy) close();
        }}
      >
        <DialogContent className="delivery-dialog">
          <DialogHeader>
            <DialogTitle>Check this delivery</DialogTitle>
            <DialogDescription>
              {review.payload.supplier} · Bill {review.payload.invoice_number}.
              First confirm the bill details; then enter what physically
              arrived. Saving this step does not add available stock.
            </DialogDescription>
          </DialogHeader>
          <ol className="receiving-progress" aria-label="Receiving steps">
            <li>
              <strong>Confirm bill</strong>
              <span>Exact parts and units below</span>
            </li>
            <li>
              <strong>Count</strong>
              <span>After this bill is saved</span>
            </li>
            <li>
              <strong>Approve</strong>
              <span>Partner checks counts</span>
            </li>
            <li>
              <strong>Ready to sell</strong>
              <span>Accepted stock available</span>
            </li>
          </ol>
          {!goods.length ? (
            <div className="check-note">
              Choose “New part” below to add the checked item here. Mixed glass
              still needs its actual variant breakdown.
            </div>
          ) : null}
          <form onSubmit={(event) => void save(event)}>
            <fieldset disabled={busy}>
              <Field label="Confirmed date printed on the invoice">
                <Input
                  name="invoice_date"
                  type="date"
                  required
                  onChange={() => setConfirmed(false)}
                />
              </Field>
              {review.payload.lines.map((line, index) => (
                <section className="delivery-item" key={index}>
                  <h3>
                    {line.description}{" "}
                    <small>Bill amount {money(line.amount_paise)}</small>
                  </h3>
                  {rows
                    .filter((row) => row.source_index === index)
                    .map((row) => (
                      <div className="counted-item" key={row.key}>
                        <div className="grid two">
                          <Field label="Exact part">
                            <NativeSelect
                              value={row.product_id}
                              required
                              onChange={(event) => {
                                const product = goods.find(
                                  (g) => g.id === event.target.value,
                                );
                                setConfirmed(false);
                                setRows((old) =>
                                  old.map((r) =>
                                    r.key === row.key
                                      ? {
                                          ...r,
                                          product_id: event.target.value,
                                          unit: product?.unit ?? "",
                                        }
                                      : r,
                                  ),
                                );
                              }}
                            >
                              <NativeSelectOption value="">
                                Choose the verified variant
                              </NativeSelectOption>
                              {goods.map((product) => (
                                <NativeSelectOption
                                  key={product.id}
                                  value={product.id}
                                >
                                  {product.name} · {product.sku}
                                </NativeSelectOption>
                              ))}
                            </NativeSelect>
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() => setNewPartRow(row.key)}
                            >
                              New part
                            </Button>
                          </Field>
                          <Field label="Quantity on the bill">
                            <Input
                              type="number"
                              min="1"
                              step="1"
                              required
                              value={row.quantity}
                              onChange={(event) =>
                                update(row.key, "quantity", event.target.value)
                              }
                            />
                          </Field>
                        </div>
                        <details
                          className="optional-fields"
                          open={!row.unit || !row.rate}
                        >
                          <summary>Unit and buying rate</summary>
                          <div className="grid two">
                            <Field label="Confirmed supplier unit">
                              <NativeSelect
                                value={row.unit}
                                onChange={(event) =>
                                  update(row.key, "unit", event.target.value)
                                }
                              >
                                <NativeSelectOption value="">
                                  Confirm piece, pair, set or pack
                                </NativeSelectOption>
                                {(() => {
                                  const product = goods.find(
                                    (p) => p.id === row.product_id,
                                  );
                                  return product
                                    ? [
                                        product.unit,
                                        ...Object.keys(product.conversions),
                                      ].map((unit) => (
                                        <NativeSelectOption
                                          key={unit}
                                          value={unit}
                                        >
                                          {unit}
                                        </NativeSelectOption>
                                      ))
                                    : null;
                                })()}
                              </NativeSelect>
                            </Field>
                            <Field label="Purchase rate per unit (₹)">
                              <Input
                                type="number"
                                min="0"
                                step="0.01"
                                value={row.rate}
                                onChange={(event) =>
                                  update(row.key, "rate", event.target.value)
                                }
                              />
                            </Field>
                          </div>
                        </details>
                        {rows.filter((r) => r.source_index === index).length >
                        1 ? (
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => {
                              setConfirmed(false);
                              setRows((old) =>
                                old.filter((r) => r.key !== row.key),
                              );
                            }}
                          >
                            Remove split
                          </Button>
                        ) : null}
                      </div>
                    ))}
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setConfirmed(false);
                      setRows((old) => [
                        ...old,
                        {
                          key: crypto.randomUUID(),
                          source_index: index,
                          product_id: "",
                          unit: "",
                          quantity: "",
                          rate: "",
                        },
                      ]);
                    }}
                  >
                    Split into another exact variant
                  </Button>
                </section>
              ))}
              <Confirmation
                checked={confirmed}
                onChange={setConfirmed}
                label="I checked the original invoice date, exact variants, units, quantities and purchase rates. Split amounts match each bill line."
              />
              {error ? (
                <p role="alert" className="form-error">
                  {error}
                </p>
              ) : null}
              <div className="actions">
                <Button type="button" variant="outline" onClick={close}>
                  Cancel
                </Button>
                <Button disabled={!goods.length || !confirmed} type="submit">
                  {busy ? "Saving…" : "Confirm bill · next: count delivery"}
                </Button>
              </div>
            </fieldset>
          </form>
        </DialogContent>
      </Dialog>
      {newPartRow ? (
        <QuickPartDialog
          post={post}
          initialName={
            review.payload.lines[
              rows.find((r) => r.key === newPartRow)!.source_index
            ].description
          }
          close={() => setNewPartRow(null)}
          onSaved={(part) => {
            setConfirmed(false);
            setRows((old) =>
              old.map((r) =>
                r.key === newPartRow
                  ? { ...r, product_id: part.id, unit: part.unit }
                  : r,
              ),
            );
          }}
        />
      ) : null}
    </>
  );
}
