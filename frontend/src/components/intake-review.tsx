import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { api, write, paise } from "@/lib/api";
import type { Draft, ShopState, DraftLine, Transaction } from "@/lib/types";

export default function IntakeReview({
  draft,
  state,
  changed,
  postable = true,
}: {
  draft: Draft;
  state: ShopState;
  changed: () => Promise<void>;
  postable?: boolean;
}) {
  const familyList = useId();
  const [families, setFamilies] = useState<{ id: string; name: string }[]>([]);
  const [payload, setPayload] = useState(draft.payload);
  const [dirty, setDirty] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ id: string; name: string }[]>("/api/v1/catalog/products?limit=100")
      .then((rows) => {
        if (active) setFamilies(rows);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  function header(key: string, value: string) {
    setPayload((p) => ({ ...p, [key]: value || null }));
    setDirty(true);
    setConfirmed(false);
  }
  function update(index: number, patch: Partial<DraftLine>) {
    setPayload((p) => ({
      ...p,
      lines: p.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    }));
    setDirty(true);
    setConfirmed(false);
  }
  async function action(post: boolean) {
    setBusy(true);
    setError("");
    try {
      if (!post) {
        await write(
          `/api/drafts/${draft.id}`,
          { version: draft.version, payload },
          "PATCH",
        );
        const saved = await api<Draft>(`/api/drafts/${draft.id}`);
        if (saved.version !== draft.version + 1)
          throw new Error("Revision not verified. Reload before continuing.");
      } else {
        if (dirty || !confirmed)
          throw new Error("Save your changes and confirm the review first.");
        await write(`/api/drafts/${draft.id}/approve`, {
          version: draft.version,
        });
        const saved = await write<Transaction>(`/api/drafts/${draft.id}/post`, {
          version: draft.version,
        });
        const checked = await api<Transaction>(`/api/transactions/${saved.id}`);
        if (
          checked.id !== saved.id ||
          checked.kind !== "purchase" ||
          checked.lines.length !== payload.lines.length
        )
          throw new Error(
            "Saved bill is not verified; reload before retrying.",
          );
        const stock = await api<ShopState>("/api/state");
        if (
          checked.lines.some(
            (l) => !stock.products.some((p) => p.id === l.product_id),
          )
        )
          throw new Error(
            "Saved parts are not verified; check Activity before retrying.",
          );
      }
      await changed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="Review the items AI prepared"
      note="Nothing is available to sell yet"
    >
      <p>
        Check the items and buying rates, set selling prices, then save the
        incoming bill. When goods reach Kakinada, use Receive stock to count and
        approve them.
      </p>
      <fieldset disabled={busy}>
        <datalist id={familyList}>
          {[...new Set(families.map((f) => f.name))].map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <div className="grid">
          <Field label="Supplier">
            <Input
              value={payload.supplier ?? ""}
              onChange={(e) => header("supplier", e.target.value)}
            />
          </Field>
          <Field label="Bill number">
            <Input
              value={payload.invoice_number ?? ""}
              onChange={(e) => header("invoice_number", e.target.value)}
            />
          </Field>
          <Field label="Printed bill date">
            <Input
              type="date"
              value={payload.invoice_date ?? ""}
              onChange={(e) => header("invoice_date", e.target.value)}
            />
          </Field>
        </div>
        {payload.lines.map((line, index) => (
          <div className="intake-item" key={index}>
            <strong>{line.description}</strong>
            <div className="grid intake-product-grid">
              <Field label="Use a saved part or create a new one">
                <NativeSelect
                  value={line.product_id ?? ""}
                  onChange={(e) =>
                    update(index, {
                      product_id: e.target.value || undefined,
                    })
                  }
                >
                  <NativeSelectOption value="">
                    New part · AI proposed below
                  </NativeSelectOption>
                  {state.products
                    .filter((p) => p.kind === "goods")
                    .map((p) => (
                      <NativeSelectOption key={p.id} value={p.id}>
                        {p.name} · {p.sku}
                      </NativeSelectOption>
                    ))}
                </NativeSelect>
              </Field>
              {!line.product_id ? (
                <Field label="Exact part name">
                  <Input
                    value={line.name ?? ""}
                    onChange={(e) => update(index, { name: e.target.value })}
                  />
                </Field>
              ) : (
                <p>
                  Uses the existing SKU and selling price. Existing catalogue
                  prices are kept.
                </p>
              )}
            </div>
            <div className="grid intake-numbers-grid">
              <Field label="Bought quantity">
                <Input
                  type="number"
                  step="1"
                  min="1"
                  value={line.quantity ?? ""}
                  onChange={(e) =>
                    update(index, {
                      quantity:
                        e.target.value === ""
                          ? undefined
                          : Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="Unit">
                <NativeSelect
                  value={line.unit ?? ""}
                  onChange={(e) =>
                    update(index, { unit: e.target.value || undefined })
                  }
                >
                  <NativeSelectOption value="">Confirm unit</NativeSelectOption>
                  {["piece", "pair", "set", "kit", "box", "carton"].map((u) => (
                    <NativeSelectOption value={u} key={u}>
                      {u}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Buying rate (₹)">
                <Input
                  inputMode="decimal"
                  defaultValue={
                    line.cost_paise === undefined || line.cost_paise === null
                      ? ""
                      : String(line.cost_paise / 100)
                  }
                  onBlur={(e) => {
                    try {
                      update(index, {
                        cost_paise:
                          e.target.value === ""
                            ? undefined
                            : paise(e.target.value),
                      });
                    } catch (err) {
                      setError((err as Error).message);
                    }
                  }}
                />
              </Field>
              {!line.product_id ? (
                <Field label="Your selling price (₹)">
                  <Input
                    inputMode="decimal"
                    placeholder="Set your price"
                    defaultValue={
                      line.selling_price_paise == null
                        ? ""
                        : String(line.selling_price_paise / 100)
                    }
                    onBlur={(e) => {
                      try {
                        update(index, {
                          selling_price_paise:
                            e.target.value === ""
                              ? null
                              : paise(e.target.value),
                        });
                      } catch (err) {
                        setError((err as Error).message);
                      }
                    }}
                  />
                </Field>
              ) : null}
            </div>
            {!line.product_id ? (
              <details className="optional-fields">
                <summary>Product family and category</summary>
                <div className="grid intake-product-grid">
                  <Field label="Product family">
                    <Input
                      value={line.family_name ?? ""}
                      list={familyList}
                      onChange={(e) =>
                        update(index, { family_name: e.target.value })
                      }
                      placeholder="Type a family, e.g. Side mirrors"
                    />
                  </Field>
                  <Field label="Category">
                    <Input
                      value={line.category ?? ""}
                      onChange={(e) =>
                        update(index, { category: e.target.value })
                      }
                    />
                  </Field>
                </div>
              </details>
            ) : null}
            {line.amount_paise != null &&
            line.quantity != null &&
            line.cost_paise != null &&
            line.quantity * line.cost_paise !== line.amount_paise ? (
              <p className="form-error">
                Quantity × buying rate does not match the source line amount.
                Correct this before approval.
              </p>
            ) : null}
            {line.issues?.length ? (
              <div className="inline-note">
                <strong>Needs your check</strong>
                <ul>
                  {line.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
                <Button
                  variant="outline"
                  onClick={() => update(index, { issues: [] })}
                >
                  I corrected these details
                </Button>
              </div>
            ) : null}
          </div>
        ))}
        <details className="optional-fields">
          <summary>Source details</summary>
          <p>{payload.source_note}</p>
        </details>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {dirty ? (
          <div className="actions">
            <span>Save corrections before approval.</span>
            <Button onClick={() => void action(false)}>
              Save items & prices
            </Button>
          </div>
        ) : (
          <>
            <Confirmation
              checked={confirmed}
              onChange={setConfirmed}
              label="I checked these exact parts, units, quantities and buying rates, and set the selling prices."
            />
            {postable ? (
              <div className="actions">
                <span>
                  Creates incoming goods. It does not confirm arrival.
                </span>
                <Button disabled={!confirmed} onClick={() => void action(true)}>
                  Approve items & save incoming bill
                </Button>
              </div>
            ) : (
              <p>
                Use the assistant approval below after reviewing this version.
              </p>
            )}
          </>
        )}
      </fieldset>
    </Panel>
  );
}
