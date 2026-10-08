import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { whole } from "@/lib/api";
import type { Post, Product } from "@/lib/types";
export default function Corrections({
  products,
  post,
}: {
  products: Product[];
  post: Post;
}) {
  const goods = products.filter((p) => p.kind === "goods");
  const [pid, setPid] = useState(goods[0]?.id ?? "");
  const p = goods.find((x) => x.id === pid);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setError("");
    setBusy(true);
    try {
      if (!confirmed)
        throw new Error("Confirm the physical count and supporting evidence.");
      await post("/api/adjustments", {
        product_id: pid,
        available: whole(String(data.get("available"))),
        damaged: whole(String(data.get("damaged"))),
        quarantined: whole(String(data.get("quarantined"))),
        reason: data.get("reason"),
        evidence: data.get("evidence"),
      });
      setConfirmed(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Count an exact SKU" note="Kakinada store">
      <form onSubmit={(e) => void save(e)}>
        <fieldset disabled={busy}>
          <Field label="SKU">
            <NativeSelect
              value={pid}
              onChange={(e) => {
                setPid(e.target.value);
                setConfirmed(false);
              }}
            >
              {goods.map((x) => (
                <NativeSelectOption value={x.id} key={x.id}>
                  {x.sku} · {x.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          {p ? (
            <>
              <p>
                Ledger now: {p.available} available · {p.damaged} damaged ·{" "}
                {p.quarantined} quarantined ({p.unit})
              </p>
              <div
                className="grid"
                key={`${p.id}:${p.available}:${p.damaged}:${p.quarantined}`}
              >
                {(["available", "damaged", "quarantined"] as const).map((k) => (
                  <Field key={k} label={`Counted ${k}`}>
                    <Input
                      name={k}
                      type="number"
                      min="0"
                      step="1"
                      defaultValue={p[k]}
                      required
                    />
                  </Field>
                ))}
              </div>
            </>
          ) : null}
          <Field label="Reason">
            <Input name="reason" required maxLength={200} />
          </Field>
          <Field label="Count evidence">
            <Input
              name="evidence"
              required
              maxLength={200}
              placeholder="Who counted, when, and supporting record"
            />
          </Field>
          <Confirmation
            checked={confirmed}
            onChange={setConfirmed}
            label="I reviewed the physical counts and authorize this correction."
          />
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
          <div className="actions">
            <span className="meta">
              The difference becomes a new audited movement.
            </span>
            <Button type="submit" disabled={!p}>
              {busy ? "Saving…" : "Post count adjustment"}
            </Button>
          </div>
        </fieldset>
      </form>
    </Panel>
  );
}
