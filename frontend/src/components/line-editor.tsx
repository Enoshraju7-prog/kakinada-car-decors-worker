import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Field } from "./shop-form";
import type { Product } from "@/lib/types";

export interface Entry {
  id: string;
  productId: string;
  quantity: string;
  unit: string;
  price: string;
}
export function newEntry(products: Product[], sale: boolean): Entry {
  const p = products[0];
  return {
    id: crypto.randomUUID(),
    productId: p?.id ?? "",
    quantity: "1",
    unit: p?.unit ?? "piece",
    price: sale && p ? (p.price_paise / 100).toFixed(2) : "",
  };
}
export function LineEditor({
  products,
  entries,
  setEntries,
  sale = false,
  disabled = false,
  onNewPart,
}: {
  products: Product[];
  entries: Entry[];
  setEntries: (entries: Entry[]) => void;
  sale?: boolean;
  disabled?: boolean;
  onNewPart?: () => void;
}) {
  function patch(id: string, changes: Partial<Entry>) {
    setEntries(entries.map((e) => (e.id === id ? { ...e, ...changes } : e)));
  }
  return (
    <>
      <div className="form-lines">
        {entries.map((entry) => {
          const product = products.find((p) => p.id === entry.productId);
          return (
            <div className={`entry ${sale ? "sale" : ""}`} key={entry.id}>
              <Field label="Exact product">
                <NativeSelect
                  aria-label="Exact product"
                  value={entry.productId}
                  onChange={(event) => {
                    const p = products.find(
                      (p) => p.id === event.target.value,
                    )!;
                    patch(entry.id, {
                      productId: p.id,
                      unit: p.unit,
                      ...(sale
                        ? { price: (p.price_paise / 100).toFixed(2) }
                        : {}),
                    });
                  }}
                >
                  {products.map((p) => (
                    <NativeSelectOption key={p.id} value={p.id}>
                      {p.name} · {p.sku}
                      {p.kind === "goods"
                        ? ` · ${p.available} ${p.unit} available`
                        : ""}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Quantity">
                <Input
                  aria-label="Quantity"
                  type="number"
                  min="1"
                  step="1"
                  required
                  value={entry.quantity}
                  onChange={(e) =>
                    patch(entry.id, { quantity: e.target.value })
                  }
                />
              </Field>
              {!sale ? (
                <Field label="Supplier unit">
                  <NativeSelect
                    aria-label="Supplier unit"
                    value={entry.unit}
                    onChange={(e) => patch(entry.id, { unit: e.target.value })}
                  >
                    {[
                      product?.unit ?? "piece",
                      ...Object.keys(product?.conversions ?? {}),
                    ].map((unit) => (
                      <NativeSelectOption key={unit}>{unit}</NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
              ) : null}
              <Field label={sale ? "Price / unit (₹)" : "Cost / unit (₹)"}>
                <Input
                  aria-label={sale ? "Price / unit (₹)" : "Cost / unit (₹)"}
                  inputMode="decimal"
                  required
                  value={entry.price}
                  onChange={(e) => patch(entry.id, { price: e.target.value })}
                />
              </Field>
              <Button
                type="button"
                variant="outline"
                className="remove"
                aria-label="Remove line"
                disabled={disabled}
                onClick={() =>
                  setEntries(entries.filter((e) => e.id !== entry.id))
                }
              >
                ×
              </Button>
            </div>
          );
        })}
      </div>
      <Button
        type="button"
        variant="outline"
        disabled={disabled || (!products.length && !onNewPart)}
        onClick={() =>
          products.length
            ? setEntries([...entries, newEntry(products, sale)])
            : onNewPart?.()
        }
      >
        + {sale ? "Add product or fitting" : "Add item"}
      </Button>
      {onNewPart && products.length ? (
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={onNewPart}
        >
          Create a new part
        </Button>
      ) : null}
    </>
  );
}
