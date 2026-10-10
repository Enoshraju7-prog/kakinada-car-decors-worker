import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shop-form";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { write, api, time, money } from "@/lib/api";

export interface Customer {
  id?: string;
  name: string;
  phone: string;
  address: string;
}
interface Purchase {
  id: string;
  created_at: string;
  total_paise: number;
  payment: string;
  items: { name: string; sku: string; quantity: number; unit: string }[];
}
export interface CustomerHistory {
  customer: Customer | null;
  purchases: Purchase[];
  has_more: boolean;
}
export const blankCustomer = (): Customer => ({
  name: "",
  phone: "",
  address: "",
});

export function CustomerDetails({
  value,
  onChange,
  disabled,
}: {
  value: Customer | null;
  onChange: (customer: Customer | null) => void;
  disabled: boolean;
}) {
  const [finding, setFinding] = useState(false);
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<CustomerHistory | null>(null);
  async function find() {
    if (!value) return;
    setFinding(true);
    setNotice("");
    setHistory(null);
    try {
      const result = await write<{ customer: Customer | null }>(
        "/api/customers/lookup",
        { phone: value.phone },
      );
      if (result.customer) {
        onChange(result.customer);
        setNotice("Saved customer found. Check the details below.");
        setHistory(
          await api<CustomerHistory>(`/api/customers/${result.customer.id}`),
        );
      } else {
        onChange({ ...value, id: undefined });
        setNotice("New customer. Enter their name; address is optional.");
      }
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setFinding(false);
    }
  }
  return (
    <section className="form-lines" aria-label="Customer details">
      <h3>Customer</h3>
      <p className="meta">
        Use their phone to find a returning customer, or choose Walk-in.
      </p>
      <Field label="Customer type">
        <NativeSelect
          value={value ? "saved" : "walk-in"}
          disabled={disabled || finding}
          onChange={(e) => {
            onChange(e.target.value === "walk-in" ? null : blankCustomer());
            setHistory(null);
            setNotice("");
          }}
        >
          <NativeSelectOption value="walk-in">
            Walk-in · no details
          </NativeSelectOption>
          <NativeSelectOption value="saved">
            Save customer details
          </NativeSelectOption>
        </NativeSelect>
      </Field>
      {value && (
        <fieldset disabled={disabled || finding}>
          <div className="grid two form-lines">
            <Field label="Mobile number">
              <Input
                type="tel"
                inputMode="tel"
                autoComplete="off"
                maxLength={30}
                required
                placeholder="10-digit mobile number"
                value={value.phone}
                onChange={(e) => {
                  onChange({ ...value, phone: e.target.value, id: undefined });
                  setHistory(null);
                  setNotice("");
                }}
              />
            </Field>
            <div className="actions">
              <Button
                type="button"
                variant="outline"
                disabled={!value.phone || finding}
                onClick={() => void find()}
              >
                {finding ? "Finding…" : "Find customer"}
              </Button>
            </div>
            <Field label="Customer name">
              <Input
                autoComplete="off"
                required
                maxLength={150}
                value={value.name}
                onChange={(e) => onChange({ ...value, name: e.target.value })}
              />
            </Field>
            <Field label="Address (optional)">
              <Input
                autoComplete="off"
                maxLength={500}
                value={value.address}
                onChange={(e) =>
                  onChange({ ...value, address: e.target.value })
                }
              />
            </Field>
          </div>
          {value.id && (
            <p className="meta">
              Changes to name or address will update this saved customer when
              you confirm the sale.
            </p>
          )}
          <p className="meta">
            Private partner record. Details are encrypted and aren’t sent to the
            AI assistant.
          </p>
        </fieldset>
      )}
      {notice && <p role="status">{notice}</p>}
      {history && <PurchaseHistory history={history} />}
    </section>
  );
}

export function PurchaseHistory({ history }: { history: CustomerHistory }) {
  return (
    <details>
      <summary>
        Previous purchases ({history.purchases.length}
        {history.has_more ? "+" : ""})
      </summary>
      {history.purchases.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Purchased on</th>
                <th>Products purchased</th>
                <th>Total</th>
                <th>Payment</th>
              </tr>
            </thead>
            <tbody>
              {history.purchases.map((p) => (
                <tr key={p.id}>
                  <td>{time(p.created_at)}</td>
                  <td>
                    {p.items.map((item, i) => (
                      <div key={`${item.sku}-${i}`}>
                        {item.name} · {item.quantity} {item.unit}
                      </div>
                    ))}
                  </td>
                  <td>{money(p.total_paise)}</td>
                  <td>{p.payment.toUpperCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No previous purchases.</p>
      )}
      {history.has_more && (
        <p className="meta">Showing the latest 20 purchases.</p>
      )}
    </details>
  );
}

export function SaleCustomer({ saleId }: { saleId: string }) {
  const [history, setHistory] = useState<CustomerHistory | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    setError("");
    try {
      setHistory(await api<CustomerHistory>(`/api/sales/${saleId}/customer`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="form-lines">
      {!history && (
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => void load()}
        >
          {busy ? "Loading…" : "View customer"}
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
      {history &&
        (history.customer ? (
          <>
            <p>
              {history.customer.name} · {history.customer.phone}
            </p>
            {history.customer.address && <p>{history.customer.address}</p>}
            <PurchaseHistory history={history} />
          </>
        ) : (
          <p>Walk-in customer · no details saved</p>
        ))}
    </div>
  );
}
