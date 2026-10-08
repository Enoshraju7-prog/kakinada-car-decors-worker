import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Confirmation, Field, Panel } from "@/components/shop-form";
import { QuickPartDialog, type SavedPart } from "@/components/quick-part";
import { istDay, paise, whole } from "@/lib/api";
import type { Product, Post } from "@/lib/types";
interface Count {
  id: string;
  product: string;
  accepted: string;
  damaged: string;
  held: string;
  cost: string;
}
export function UnbilledReceiving({
  products,
  post,
}: {
  products: Product[];
  post: Post;
}) {
  const goods = products.filter((p) => p.kind === "goods");
  const newReference = () =>
    `DEL-${istDay()}-${crypto.randomUUID().slice(0, 8).toUpperCase()}`;
  const [reference, setReference] = useState(newReference);
  const [rows, setRows] = useState<Count[]>([]);
  const [addingPart, setAddingPart] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  function patch(id: string, changes: Partial<Count>) {
    setConfirmed(false);
    setRows((old) => old.map((r) => (r.id === id ? { ...r, ...changes } : r)));
  }
  function add(part?: SavedPart) {
    setConfirmed(false);
    setRows((old) => [
      ...old,
      {
        id: crypto.randomUUID(),
        product: part?.id ?? "",
        accepted: "",
        damaged: "0",
        held: "0",
        cost: part?.cost ?? "",
      },
    ]);
    setSaved(false);
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setSaved(false);
    const form = e.currentTarget;
    const data = new FormData(form);
    try {
      if (!confirmed || !rows.length)
        throw new Error(
          "Add the counted items and confirm they are at the shop.",
        );
      const lines = rows.map((r) => {
        const product = goods.find((p) => p.id === r.product);
        if (!product) throw new Error("Choose a part for every row.");
        return {
          product_id: product.id,
          unit: product.unit,
          accepted: whole(r.accepted),
          damaged: whole(r.damaged),
          quarantined: whole(r.held),
          cost_paise: r.cost.trim() === "" ? null : paise(r.cost),
        };
      });
      setBusy(true);
      await post("/api/unbilled-receipts", {
        supplier: String(data.get("supplier")),
        reference,
        received_date: String(data.get("date")),
        evidence: String(data.get("evidence")),
        confirmed,
        lines,
      });
      form.reset();
      setRows([]);
      setConfirmed(false);
      setSaved(true);
      setReference(newReference());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Panel
        title="Goods arrived without a bill"
        note="Count → approve → ready to sell"
      >
        <p>
          Use only for goods already at the shop, without a bill or an order
          recorded here.
        </p>
        <form onSubmit={(e) => void save(e)}>
          <fieldset disabled={busy}>
            <Field label="Where did you buy these goods?">
              <Input
                name="supplier"
                placeholder="Vendor or source name"
                required
                maxLength={200}
              />
            </Field>
            {rows.map((r) => {
              const product = goods.find((p) => p.id === r.product);
              return (
                <section key={r.id} className="counted-item">
                  <div className="grid two">
                    <Field label="Part">
                      <NativeSelect
                        value={r.product}
                        onChange={(e) =>
                          patch(r.id, { product: e.target.value })
                        }
                        required
                      >
                        <NativeSelectOption value="">
                          Choose a part
                        </NativeSelectOption>
                        {goods.map((p) => (
                          <NativeSelectOption key={p.id} value={p.id}>
                            {p.name} · {p.unit}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Field>
                    <Field
                      label={`Good condition (${product?.unit ?? "units"})`}
                    >
                      <Input
                        type="number"
                        min="0"
                        step="1"
                        required
                        value={r.accepted}
                        onChange={(e) =>
                          patch(r.id, { accepted: e.target.value })
                        }
                        placeholder="Count ready to sell"
                      />
                    </Field>
                  </div>
                  <details className="optional-fields">
                    <summary>
                      Damaged, on hold or buying price (optional)
                    </summary>
                    <div className="grid">
                      <Field label="Damaged">
                        <Input
                          type="number"
                          min="0"
                          step="1"
                          value={r.damaged}
                          onChange={(e) =>
                            patch(r.id, { damaged: e.target.value })
                          }
                        />
                      </Field>
                      <Field label="On hold">
                        <Input
                          type="number"
                          min="0"
                          step="1"
                          value={r.held}
                          onChange={(e) =>
                            patch(r.id, { held: e.target.value })
                          }
                        />
                      </Field>
                      <Field label="Buying price (₹ per unit)">
                        <Input
                          inputMode="decimal"
                          value={r.cost}
                          onChange={(e) =>
                            patch(r.id, { cost: e.target.value })
                          }
                          placeholder="Leave blank if unknown"
                        />
                      </Field>
                    </div>
                  </details>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setConfirmed(false);
                      setRows((old) => old.filter((x) => x.id !== r.id));
                    }}
                  >
                    Remove item
                  </Button>
                </section>
              );
            })}
            {!goods.length ? (
              <p>
                No parts added yet. Create your first part below, then enter its
                count.
              </p>
            ) : null}
            <div className="receiving-options">
              <Button
                type="button"
                variant="outline"
                onClick={() => (goods.length ? add() : setAddingPart(true))}
              >
                Add counted item
              </Button>
              {goods.length ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAddingPart(true)}
                >
                  Create a new part
                </Button>
              ) : null}
            </div>
            <details className="optional-fields">
              <summary>Delivery date and notes</summary>
              <div className="grid two">
                <Field label="Date goods arrived">
                  <Input
                    name="date"
                    type="date"
                    defaultValue={istDay()}
                    required
                    onChange={() => setConfirmed(false)}
                  />
                </Field>
                <Field label="Delivery reference">
                  <Input
                    value={reference}
                    onChange={(e) => {
                      setConfirmed(false);
                      setReference(e.target.value);
                    }}
                    required
                    maxLength={100}
                  />
                </Field>
                <Field label="Delivery note">
                  <Input
                    name="evidence"
                    defaultValue="Partner counted goods at the shop; supplier did not supply a bill"
                    required
                    maxLength={1000}
                    onChange={() => setConfirmed(false)}
                  />
                </Field>
              </div>
            </details>
            <Confirmation
              checked={confirmed}
              onChange={setConfirmed}
              label="These goods are at the shop. I checked the parts and counts, and this delivery is not already recorded."
            />
            {error ? (
              <p role="alert" className="form-error">
                {error}
              </p>
            ) : null}
            {saved ? (
              <p role="status">
                Stock added and verified. You can now make a sale.
              </p>
            ) : null}
            <div className="actions">
              <span className="meta">
                Only good-condition items become available. Blank buying price
                stays unknown.
              </span>
              <Button type="submit" disabled={!confirmed || !rows.length}>
                {busy ? "Saving…" : "Approve & add stock"}
              </Button>
            </div>
          </fieldset>
        </form>
      </Panel>
      {addingPart ? (
        <QuickPartDialog
          post={post}
          close={() => setAddingPart(false)}
          onSaved={add}
        />
      ) : null}
    </>
  );
}
