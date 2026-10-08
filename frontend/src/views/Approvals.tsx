import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { api, write, money, paise } from "@/lib/api";
import type { Draft, ShopState, DraftLine } from "@/lib/types";
import IntakeReview from "@/components/intake-review";

export function DraftReview({
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
  const [payload, setPayload] = useState(draft.payload);
  const [rates, setRates] = useState<Record<number, string>>({});
  const [editing, setEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const partner = state.role === "partner";
  const lineName = (line: DraftLine) =>
    state.products.find((p) => p.id === line.product_id)?.name ??
    state.incoming_transactions
      .flatMap((t) => t.lines)
      .find((l) => l.id === line.purchase_line_id)?.snapshot.name ??
    line.purchase_line_id ??
    "Unresolved SKU";
  const update = (index: number, key: string, value: unknown) =>
    setPayload((p) => ({
      ...p,
      lines: p.lines.map((l, i) => (i === index ? { ...l, [key]: value } : l)),
    }));
  async function action(kind: "edit" | "approve_and_post") {
    setBusy(true);
    setError("");
    try {
      if (kind === "edit") {
        const corrected = {
          ...payload,
          lines: payload.lines.map((line, index) => {
            for (const value of draft.kind === "receipt"
              ? [line.accepted ?? 0, line.damaged ?? 0, line.quarantined ?? 0]
              : [line.quantity]) {
              if (
                !Number.isSafeInteger(value) ||
                (value ?? -1) < (draft.kind === "receipt" ? 0 : 1)
              )
                throw new Error("Enter valid whole quantities before saving.");
            }
            return rates[index] === undefined
              ? line
              : { ...line, cost_paise: paise(rates[index]) };
          }),
        };

        await write(
          `/api/drafts/${draft.id}`,
          { version: draft.version, payload: corrected },
          "PATCH",
        );
        setEditing(false);
        setConfirmed(false);
      } else {
        if (!confirmed)
          throw new Error(
            "Confirm the reviewed quantities and exact units first.",
          );
        if (draft.status !== "approved")
          await write(`/api/drafts/${draft.id}/approve`, {
            version: draft.version,
          });
        const saved = await write<{ id: string }>(
          `/api/drafts/${draft.id}/post`,
          { version: draft.version },
        );
        {
          const readback = await api<{ id: string }>(
            `/api/transactions/${saved.id}`,
          );
          if (readback.id !== saved.id)
            throw new Error(
              "Posting readback failed; check saved history before retrying.",
            );
        }
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
      title={
        draft.kind === "receipt"
          ? "Step 3 · review received goods"
          : "Supplier bill draft"
      }
      note={`${draft.actor} · ${draft.status === "approved" ? "Approved · awaiting save" : "Needs review"}`}
    >
      <fieldset disabled={busy}>
        {draft.kind === "purchase" ? (
          <div className="grid">
            {(["supplier", "invoice_number", "invoice_date"] as const).map(
              (k) => (
                <Field key={k} label={k.replaceAll("_", " ")}>
                  {editing ? (
                    <Input
                      value={payload[k] ?? ""}
                      onChange={(e) =>
                        setPayload((p) => ({ ...p, [k]: e.target.value }))
                      }
                      type={k === "invoice_date" ? "date" : "text"}
                    />
                  ) : (
                    <strong>{payload[k]}</strong>
                  )}
                </Field>
              ),
            )}
          </div>
        ) : (
          <p>
            {(() => {
              const bill = state.incoming_transactions.find(
                (t) => t.id === payload.purchase_id,
              );
              return bill
                ? `Supplier: ${bill.data.supplier} · Bill ${bill.data.invoice_number}`
                : "Check the received counts against the supplier bill.";
            })()}
          </p>
        )}
        {payload.lines.map((line, index) => (
          <div className="draft-line" key={index}>
            <strong>{lineName(line)}</strong>
            {editing && draft.kind === "purchase" ? (
              <Field label="Exact SKU">
                <NativeSelect
                  value={line.product_id}
                  onChange={(e) => update(index, "product_id", e.target.value)}
                >
                  {state.products
                    .filter((p) => p.kind === "goods")
                    .map((p) => (
                      <NativeSelectOption key={p.id} value={p.id}>
                        {p.sku} · {p.name}
                      </NativeSelectOption>
                    ))}
                </NativeSelect>
              </Field>
            ) : null}
            {draft.kind === "receipt" ? (
              (["accepted", "damaged", "quarantined"] as const).map((k) => (
                <Field
                  key={k}
                  label={
                    k === "quarantined"
                      ? "On hold"
                      : k === "accepted"
                        ? "Good condition / ready to sell"
                        : "Damaged"
                  }
                >
                  {editing ? (
                    <Input
                      type="number"
                      min="0"
                      step="1"
                      value={line[k] ?? 0}
                      onChange={(e) => update(index, k, Number(e.target.value))}
                    />
                  ) : (
                    <span>{line[k] ?? 0}</span>
                  )}
                </Field>
              ))
            ) : (
              <>
                <Field label="Printed quantity">
                  {editing ? (
                    <Input
                      type="number"
                      min="1"
                      step="1"
                      value={line.quantity}
                      onChange={(e) =>
                        update(index, "quantity", Number(e.target.value))
                      }
                    />
                  ) : (
                    <span>{line.quantity}</span>
                  )}
                </Field>
                <Field label="Printed unit">
                  {editing ? (
                    <Input
                      value={line.unit}
                      onChange={(e) => update(index, "unit", e.target.value)}
                    />
                  ) : (
                    <span>{line.unit}</span>
                  )}
                </Field>
                <Field label="Purchase rate">
                  {editing ? (
                    <Input
                      value={
                        rates[index] ?? String((line.cost_paise ?? 0) / 100)
                      }
                      inputMode="decimal"
                      onChange={(e) =>
                        setRates((r) => ({ ...r, [index]: e.target.value }))
                      }
                    />
                  ) : (
                    <span>{money(line.cost_paise ?? 0)}</span>
                  )}
                </Field>
              </>
            )}
          </div>
        ))}
        {partner && !editing ? (
          <Confirmation
            checked={confirmed}
            onChange={setConfirmed}
            label={
              draft.kind === "receipt"
                ? "I checked the actual delivery. Good-condition, damaged and on-hold counts are correct."
                : "I checked supplier identity, invoice number/date, exact SKUs, printed units and purchase rates."
            }
          />
        ) : null}
        {error ? (
          <div className="form-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="actions">
          <small>Reference: {draft.id}</small>
          <div className="button-row">
            {editing ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => {
                    setPayload(draft.payload);
                    setRates({});
                    setError("");
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
                <Button onClick={() => void action("edit")}>
                  Save revision
                </Button>
              </>
            ) : (
              <>
                <Button
                  disabled={!partner && draft.actor !== state.actor}
                  variant="outline"
                  onClick={() => {
                    setEditing(true);
                    setConfirmed(false);
                  }}
                >
                  Edit draft
                </Button>
                {partner && postable ? (
                  <Button
                    disabled={!confirmed}
                    onClick={() => void action("approve_and_post")}
                  >
                    {draft.kind === "receipt"
                      ? "Approve & make stock available"
                      : "Approve & record incoming bill"}
                  </Button>
                ) : null}
              </>
            )}
          </div>
        </div>
      </fieldset>
    </Panel>
  );
}
export default function Approvals({
  state,
  refresh,
}: {
  state: ShopState;
  refresh: () => Promise<void>;
}) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState("");
  async function load() {
    try {
      setDrafts(await api<Draft[]>("/api/drafts"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    let active = true;
    api<Draft[]>("/api/drafts")
      .then((d) => {
        if (active) setDrafts(d);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function changed() {
    await load();
    await refresh();
  }
  return (
    <>
      {error ? (
        <div className="form-error" role="alert">
          {error}
        </div>
      ) : null}
      <div className="section-top">
        <p>
          Final step: check the counts, tick the confirmation and choose
          “Approve & make stock available”. Only good-condition items become
          sellable; damaged and on-hold items stay separate.
        </p>
        <Button variant="outline" onClick={() => void load()}>
          Refresh drafts
        </Button>
      </div>
      {drafts.map((d) =>
        d.kind === "intake" ? (
          <IntakeReview
            key={`${d.id}:${d.version}:${d.status}`}
            draft={d}
            state={state}
            changed={changed}
          />
        ) : (
          <DraftReview
            key={`${d.id}:${d.version}:${d.status}`}
            draft={d}
            state={state}
            changed={changed}
          />
        ),
      )}
      {!drafts.length ? (
        <div className="panel empty">No drafts awaiting review.</div>
      ) : null}
    </>
  );
}
