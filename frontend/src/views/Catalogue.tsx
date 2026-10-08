import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { api, paise, whole } from "@/lib/api";
import type { Post, Product } from "@/lib/types";
import { PriceEditor } from "@/components/price-editor";
import { QuickPart } from "@/components/quick-part";
interface Category {
  id: string;
  name: string;
  threshold: number;
  parent_id?: string;
}
interface Family {
  id: string;
  category_id: string;
  name: string;
  brand: string;
  kind: "goods" | "service";
}
const units = ["piece", "pair", "set", "kit", "box", "carton"];
export default function Catalogue({
  post,
  products,
}: {
  post: Post;
  products: Product[];
}) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [families, setFamilies] = useState<Family[]>([]);
  const [familyId, setFamilyId] = useState("");
  const [status, setStatus] = useState("unknown");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const family = families.find((f) => f.id === familyId);
  const kind = family?.kind ?? "goods";
  async function load() {
    const [c, f] = await Promise.all([
      api<Category[]>("/api/v1/catalog/categories?limit=100"),
      api<Family[]>("/api/v1/catalog/products?limit=100"),
    ]);
    setCategories(c);
    setFamilies(f);
    setFamilyId((old) => old || f[0]?.id || "");
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Category[]>("/api/v1/catalog/categories?limit=100"),
      api<Family[]>("/api/v1/catalog/products?limit=100"),
    ])
      .then(([c, f]) => {
        if (active) {
          setCategories(c);
          setFamilies(f);
          setFamilyId(f[0]?.id ?? "");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function save(
    e: FormEvent<HTMLFormElement>,
    operation: "categories" | "products" | "variants",
  ) {
    e.preventDefault();
    const form = e.currentTarget;
    const d = new FormData(form);
    const text = (k: string) => String(d.get(k) ?? "");
    setBusy(true);
    setError("");
    try {
      let payload: unknown;
      if (operation === "categories")
        payload = {
          name: text("name"),
          parent_id: text("parent_id") || null,
          threshold: whole(text("threshold")),
        };
      else if (operation === "products")
        payload = {
          name: text("name"),
          category_id: text("category_id"),
          brand: text("brand"),
          kind: text("kind"),
        };
      else {
        if (!confirmed)
          throw new Error(
            "Confirm the exact SKU, fitment and pack conversion.",
          );
        const pack = text("pack");
        payload = {
          product_id: familyId,
          sku: text("sku"),
          name: text("name"),
          unit: text("unit"),
          model: text("model"),
          color: text("color"),
          specification: text("specification"),
          compatibility_status: status,
          compatibility: text("compatibility"),
          fitments:
            status === "specific"
              ? [
                  {
                    make: text("make"),
                    model: text("vehicle_model"),
                    generation: text("generation"),
                    year_from: text("year_from")
                      ? whole(text("year_from"))
                      : null,
                    year_to: text("year_to") ? whole(text("year_to")) : null,
                  },
                ]
              : [],
          threshold: text("threshold") ? whole(text("threshold")) : null,
          price_paise: paise(text("price")),
          conversions: pack ? { [pack]: whole(text("factor")) } : {},
          conversion_evidence: text("conversion_evidence") || "No conversion",
        };
      }
      await post(`/api/v1/catalog/${operation}`, payload);
      form.reset();
      setConfirmed(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <QuickPart post={post} onSaved={() => void load()} />
      <PriceEditor products={products} post={post} />
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <details className="optional-fields">
        <summary>
          Advanced catalogue: families, compatibility and pack conversions
        </summary>
        <Panel
          title="Add an exact SKU"
          note="Stock belongs to the variant, never to the family"
        >
          <form onSubmit={(e) => void save(e, "variants")}>
            <fieldset disabled={busy}>
              <div className="grid two">
                <Field label="Product family">
                  <NativeSelect
                    value={familyId}
                    onChange={(e) => {
                      setFamilyId(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    <NativeSelectOption value="">
                      {families.length
                        ? "Choose a saved family"
                        : "Add a family using the form above"}
                    </NativeSelectOption>
                    {families.map((f) => (
                      <NativeSelectOption value={f.id} key={f.id}>
                        {f.name} · {f.brand} ({f.kind})
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="SKU / internal code">
                  <Input name="sku" required maxLength={80} />
                </Field>
                <Field label="Exact variant name">
                  <Input name="name" required maxLength={200} />
                </Field>
                <Field label="Model / part code">
                  <Input name="model" maxLength={100} />
                </Field>
                <Field label="Colour">
                  <Input name="color" maxLength={100} />
                </Field>
                <Field label="Specification">
                  <Input name="specification" maxLength={200} />
                </Field>
                <Field label="Base selling unit">
                  <NativeSelect name="unit" key={kind}>
                    {(kind === "service" ? ["service"] : units).map((u) => (
                      <NativeSelectOption key={u}>{u}</NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Shortage threshold override">
                  <Input
                    name="threshold"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="Blank: inherit category default"
                  />
                </Field>
                <Field label="Selling price per base unit (₹)">
                  <Input
                    name="price"
                    inputMode="decimal"
                    defaultValue="0"
                    required
                  />
                </Field>
                <Field label="Compatibility status">
                  <NativeSelect
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    {["unknown", "universal", "specific"].map((x) => (
                      <NativeSelectOption key={x}>{x}</NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Compatibility notes">
                  <Input name="compatibility" maxLength={200} />
                </Field>
                {status === "specific" ? (
                  <>
                    <Field label="Vehicle make">
                      <Input name="make" required />
                    </Field>
                    <Field label="Vehicle model">
                      <Input name="vehicle_model" required />
                    </Field>
                    <Field label="Generation">
                      <Input name="generation" />
                    </Field>
                    <Field label="Year from">
                      <Input
                        name="year_from"
                        type="number"
                        min="1900"
                        max="2100"
                      />
                    </Field>
                    <Field label="Year to">
                      <Input
                        name="year_to"
                        type="number"
                        min="1900"
                        max="2100"
                      />
                    </Field>
                  </>
                ) : null}
                <Field label="Confirmed supplier pack unit">
                  <NativeSelect
                    name="pack"
                    key={kind}
                    defaultValue=""
                    disabled={kind === "service"}
                  >
                    <NativeSelectOption value="">
                      No conversion configured
                    </NativeSelectOption>
                    {units.map((u) => (
                      <NativeSelectOption key={u}>{u}</NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Base units per supplier pack">
                  <Input
                    name="factor"
                    type="number"
                    min="1"
                    step="1"
                    disabled={kind === "service"}
                  />
                </Field>
                <Field label="Conversion confirmation evidence">
                  <Input
                    name="conversion_evidence"
                    maxLength={200}
                    disabled={kind === "service"}
                    placeholder="Supplier packaging / confirmed by whom"
                  />
                </Field>
              </div>
              <Confirmation
                checked={confirmed}
                onChange={setConfirmed}
                label="I checked the exact SKU, compatibility and any packaging conversion."
              />
              <div className="actions">
                <span className="meta">
                  Unknown compatibility never means universal.
                </span>
                <Button type="submit" disabled={!family}>
                  {busy ? "Saving…" : "Save SKU"}
                </Button>
              </div>
            </fieldset>
          </form>
        </Panel>
        <div className="grid two">
          <Panel title="New product family" note="No stock quantity">
            <form onSubmit={(e) => void save(e, "products")}>
              <fieldset disabled={busy}>
                <Field label="Family name">
                  <Input name="name" required maxLength={200} />
                </Field>
                <Field label="Category">
                  <NativeSelect name="category_id">
                    {categories.map((c) => (
                      <NativeSelectOption key={c.id} value={c.id}>
                        {c.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Brand">
                  <Input name="brand" maxLength={100} />
                </Field>
                <Field label="Kind">
                  <NativeSelect name="kind">
                    <NativeSelectOption value="goods">Goods</NativeSelectOption>
                    <NativeSelectOption value="service">
                      Service
                    </NativeSelectOption>
                  </NativeSelect>
                </Field>
                <div className="actions">
                  <Button type="submit" disabled={!categories.length}>
                    Save family
                  </Button>
                </div>
              </fieldset>
            </form>
          </Panel>
          <Panel title="New category" note="Organizes families">
            <form onSubmit={(e) => void save(e, "categories")}>
              <fieldset disabled={busy}>
                <Field label="Category name">
                  <Input name="name" required maxLength={200} />
                </Field>
                <Field label="Parent category">
                  <NativeSelect name="parent_id">
                    <NativeSelectOption value="">
                      Root category
                    </NativeSelectOption>
                    {categories.map((c) => (
                      <NativeSelectOption key={c.id} value={c.id}>
                        {c.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Default shortage threshold">
                  <Input
                    name="threshold"
                    type="number"
                    min="0"
                    step="1"
                    defaultValue="0"
                    required
                  />
                </Field>
                <div className="actions">
                  <Button type="submit">Save category</Button>
                </div>
              </fieldset>
            </form>
          </Panel>
        </div>
      </details>
    </>
  );
}
