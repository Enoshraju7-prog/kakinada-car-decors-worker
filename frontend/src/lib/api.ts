interface ProductPrices {
  price_paise: number;
  purchase_price_paise: number | null;
}
import type { ShopState, Transaction, User, Draft } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
let csrf = "";
export function setSession(user: User | null) {
  csrf = user?.csrf ?? "";
}
export async function restoreSession() {
  const user = await api<User>("/api/auth/me");
  setSession(user);
  return user;
}
export async function signIn(username: string, password: string) {
  const user = await api<User>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  setSession(user);
  return user;
}
export const write = <T>(path: string, payload: unknown, method = "POST") =>
  api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.method && !["GET", "HEAD"].includes(options.method))
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && path != "/api/auth/login") {
    setSession(null);
    window.dispatchEvent(new Event("kcd-session-expired"));
  }
  const body = await response.json();
  if (!response.ok)
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : "Check the required fields and valid whole quantities.",
      response.status,
    );
  return body as T;
}
export const readState = (offset = 0) =>
  api<ShopState>(`/api/state?offset=${offset}`);
const pending = new Map<string, string>();
export async function postVerified(path: string, payload: unknown) {
  const fingerprint = JSON.stringify([path, payload]);
  const digest = [
    ...new Uint8Array(
      await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(fingerprint),
      ),
    ),
  ]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
  const storageKey = `kcd-pending-v1:${digest}`;
  let key = pending.get(digest);
  try {
    key ??= sessionStorage.getItem(storageKey) ?? undefined;
  } catch {
    /* In-memory retry still works. */
  }
  key ??= crypto.randomUUID();
  pending.set(digest, key);
  try {
    sessionStorage.setItem(storageKey, key);
  } catch {
    /* Storage may be disabled. */
  }
  try {
    const result = await api<{ id: string }>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify(payload),
    });
    if (path.startsWith("/api/agent/runs")) {
      const saved = await api<{
        id: string;
        goal: string;
        attachments: string[];
      }>(`/api/agent/runs/${result.id}`);
      if (
        saved.id !== result.id ||
        (path === "/api/agent/runs" &&
          saved.goal !== (payload as { goal: string }).goal.trim())
      )
        throw new Error("Goal readback failed; retry the same details.");
    } else if (path === "/api/receipt-drafts") {
      const saved = await api<Draft>(`/api/drafts/${result.id}`);
      const expected = payload as Draft["payload"];
      const counts = (lines: Draft["payload"]["lines"]) =>
        lines.map((l) => [
          l.purchase_line_id,
          l.accepted,
          l.damaged ?? 0,
          l.quarantined ?? 0,
        ]);
      if (
        saved.kind !== "receipt" ||
        saved.payload.purchase_id !== expected.purchase_id ||
        saved.payload.confirmed !== expected.confirmed ||
        JSON.stringify(counts(saved.payload.lines)) !==
          JSON.stringify(counts(expected.lines))
      )
        throw new Error("Draft readback failed. Retry the same details.");
    } else if (path === "/api/prices") {
      const saved = await api<ProductPrices>(
        `/api/v1/catalog/variants/${result.id}`,
      );
      const expected = payload as ProductPrices;
      if (
        saved.price_paise !== expected.price_paise ||
        saved.purchase_price_paise !== expected.purchase_price_paise
      )
        throw new Error("Price readback failed. Retry the same details.");
    } else if (path.startsWith("/api/v1/catalog/")) {
      const saved = await api<{ id: string }>(`${path}/${result.id}`);
      if (saved.id !== result.id) throw new Error("Catalogue readback failed.");
    } else if (path !== "/api/products") {
      const saved = await api<Transaction>(`/api/transactions/${result.id}`);
      const written = result as Transaction;
      if (
        JSON.stringify(
          saved.lines.map((l) => [
            l.id,
            l.quantity,
            l.damaged,
            l.quarantined ?? 0,
          ]),
        ) !==
        JSON.stringify(
          written.lines.map((l) => [
            l.id,
            l.quantity,
            l.damaged,
            l.quarantined ?? 0,
          ]),
        )
      )
        throw new Error(
          "Saved transaction verification failed. Retry the same details.",
        );
    }
    if (path === "/api/sales" && (payload as { customer?: unknown }).customer) {
      const expected = (
        payload as {
          customer: {
            id?: string;
            name: string;
            phone: string;
            address: string;
          };
        }
      ).customer;
      const saved = await api<{
        customer: {
          id: string;
          name: string;
          phone: string;
          address: string;
        } | null;
      }>(`/api/sales/${result.id}/customer`);
      const digits = expected.phone.replace(/\D/g, "");
      const mobile =
        digits.length === 12 && digits.startsWith("91")
          ? digits.slice(2)
          : digits.length === 11 && digits.startsWith("0")
            ? digits.slice(1)
            : digits;
      if (
        !saved.customer ||
        saved.customer.name !== expected.name.trim() ||
        saved.customer.address !== expected.address.trim() ||
        saved.customer.phone !== "+91" + mobile ||
        (expected.id && saved.customer.id !== expected.id)
      ) {
        throw new Error(
          "Saved customer verification failed. Retry the same sale details.",
        );
      }
    }
    const state = await readState();
    if (
      path === "/api/products" &&
      !state.products.some((p) => p.id === result.id)
    )
      throw new Error("Product readback failed. Retry the same details.");
    pending.delete(digest);
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      /* No ledger is stored in the browser. */
    }
    return { id: result.id, state };
  } catch (error) {
    if (error instanceof ApiError && error.status && error.status < 500) {
      pending.delete(digest);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        /* optional */
      }
    }
    throw error;
  }
}
export const money = (value: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    value / 100,
  );
export function paise(value: string) {
  if (!/^\d+(\.\d{1,2})?$/.test(value))
    throw new Error(
      "Enter a non-negative rupee amount with at most two decimal places.",
    );
  const [whole, fraction = ""] = value.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}
export function whole(value: string) {
  if (!/^\d+$/.test(value))
    throw new Error("Quantity must be an explicit whole number.");
  return Number(value);
}
export const istDay = (value: Date | string = new Date()) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
export const time = (value: string) =>
  new Date(value).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
