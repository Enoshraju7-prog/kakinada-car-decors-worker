import { useState, type FormEvent } from "react";
import { Panel, Field } from "@/components/shop-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { paise } from "@/lib/api";
import type { Product, Post } from "@/lib/types";

export function PriceEditor({
  products,
  post,
}: {
  products: Product[];
  post: Post;
}) {
  const [id, setId] = useState(products[0]?.id ?? "");
  const product = products.find((p) => p.id === id);
  return (
    <Panel
      title="Purchase & selling prices"
      note="Partner controls · per base unit"
    >
      <Field label="Choose item">
        <NativeSelect value={id} onChange={(e) => setId(e.target.value)}>
          {products.map((p) => (
            <NativeSelectOption key={p.id} value={p.id}>
              {p.name} · {p.sku}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Field>
      {product ? (
        <PriceForm
          key={`${product.id}:${product.price_paise}:${product.purchase_price_paise}`}
          product={product}
          post={post}
        />
      ) : (
        <p>Add an item first.</p>
      )}
    </Panel>
  );
}

function PriceForm({ product, post }: { product: Product; post: Post }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const cost = String(data.get("cost") ?? "").trim();
      await post("/api/prices", {
        id: product.id,
        price_paise: paise(String(data.get("selling"))),
        purchase_price_paise: cost === "" ? null : paise(cost),
        expected_price_paise: product.price_paise,
        expected_purchase_price_paise: product.purchase_price_paise ?? null,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={(e) => void save(e)}>
      <fieldset disabled={busy}>
        <div className="grid two form-lines">
          <Field label={`Purchase price / ${product.unit} (₹)`}>
            <Input
              name="cost"
              inputMode="decimal"
              defaultValue={
                product.purchase_price_paise == null
                  ? ""
                  : (product.purchase_price_paise / 100).toFixed(2)
              }
              placeholder="Unknown — leave blank"
            />
          </Field>
          <Field label={`Selling price / ${product.unit} (₹)`}>
            <Input
              name="selling"
              inputMode="decimal"
              defaultValue={(product.price_paise / 100).toFixed(2)}
              required
            />
          </Field>
        </div>
        <p>
          Purchase price is a confirmed reference cost. Supplier bill costs and
          completed sale prices keep their original values. Profit reporting
          comes later.
        </p>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <Button type="submit">{busy ? "Saving…" : "Save prices"}</Button>
        </div>
      </fieldset>
    </form>
  );
}
