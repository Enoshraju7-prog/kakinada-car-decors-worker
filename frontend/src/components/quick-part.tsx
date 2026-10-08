import { useEffect, useId, useState, type FormEvent } from "react";
import { Panel, Field } from "@/components/shop-form";
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
import { api, paise } from "@/lib/api";
import type { Post } from "@/lib/types";
export interface SavedPart {
  id: string;
  unit: string;
  price: string;
  cost: string;
}
export function QuickPart({
  post,
  initialName = "",
  onSaved,
}: {
  post: Post;
  initialName?: string;
  onSaved?: (part: SavedPart) => void;
}) {
  const familyList = useId();
  const [families, setFamilies] = useState<{ id: string; name: string }[]>([]);
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
  const [sku, setSku] = useState(
    () => `KCD-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const d = new FormData(form);
    setError("");
    setMessage("");
    try {
      setBusy(true);
      const unit = String(d.get("unit"));
      const price = String(d.get("price"));
      const cost = String(d.get("cost") ?? "").trim();
      const result = await post("/api/products", {
        sku,
        family_name: String(d.get("family") || "").trim() || null,
        name: String(d.get("name")),
        category: String(d.get("category") || "Accessories"),
        unit,
        kind: "goods",
        price_paise: paise(price),
        purchase_price_paise: cost ? paise(cost) : null,
      });
      form.reset();
      setSku(`KCD-${crypto.randomUUID().slice(0, 8).toUpperCase()}`);
      setMessage("Part saved. Count its delivery to make stock available.");
      onSaved?.({ id: result.id, unit, price, cost });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Add a new part" note="No stock added yet">
      <p>
        Include the car model, side or size when it identifies a different part.
      </p>
      <form onSubmit={(e) => void save(e)}>
        <fieldset disabled={busy}>
          <div className="grid two">
            <Field label="Part name">
              <Input
                name="name"
                defaultValue={initialName}
                required
                maxLength={200}
                placeholder="e.g. Alto left mirror"
              />
            </Field>
            <Field label="Product family (optional)">
              <Input
                name="family"
                list={familyList}
                maxLength={200}
                placeholder="Type a family, e.g. Side mirrors"
              />
              <datalist id={familyList}>
                {[...new Set(families.map((f) => f.name))].map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <small>
                A saved family appears here next time. The exact part still
                keeps its own stock.
              </small>
            </Field>
            <Field label="How do you count it?">
              <NativeSelect name="unit" required defaultValue="">
                <NativeSelectOption value="">
                  Choose piece, pair or set
                </NativeSelectOption>
                {["piece", "pair", "set", "kit", "box", "carton"].map((u) => (
                  <NativeSelectOption key={u} value={u}>
                    {u}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <small>
                A pair or pack stays one unit unless you confirm a conversion.
              </small>
            </Field>
            <Field label="Selling price (₹ per unit)">
              <Input
                name="price"
                type="number"
                min="0"
                step="0.01"
                required
                inputMode="decimal"
              />
            </Field>
            <Field label="Buying price (₹ per unit, optional)">
              <Input
                name="cost"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                placeholder="Leave blank if unknown"
              />
            </Field>
          </div>
          <details className="optional-fields">
            <summary>Category and item code (optional)</summary>
            <div className="grid two">
              <Field label="Category">
                <Input
                  name="category"
                  defaultValue="Accessories"
                  maxLength={80}
                />
              </Field>
              <Field label="Item code">
                <Input
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  required
                  maxLength={80}
                />
              </Field>
            </div>
          </details>
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
          {message ? <p role="status">{message}</p> : null}
          <div className="actions">
            <Button type="submit">{busy ? "Saving…" : "Save part"}</Button>
          </div>
        </fieldset>
      </form>
    </Panel>
  );
}
export function QuickPartDialog({
  post,
  initialName,
  close,
  onSaved,
}: {
  post: Post;
  initialName?: string;
  close: () => void;
  onSaved: (part: SavedPart) => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className="part-dialog">
        <DialogHeader>
          <DialogTitle>Create a part</DialogTitle>
          <DialogDescription>
            Save it here and continue your delivery without leaving this page.
          </DialogDescription>
        </DialogHeader>
        <QuickPart
          post={post}
          initialName={initialName}
          onSaved={(part) => {
            onSaved(part);
            close();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
