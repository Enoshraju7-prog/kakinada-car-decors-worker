export type Unit =
  "piece" | "pair" | "set" | "kit" | "box" | "carton" | "service";
export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  brand: string;
  model: string;
  compatibility: string;
  specification: string;
  kind: "goods" | "service";
  unit: Unit;
  threshold: number;
  price_paise: number;
  purchase_price_paise?: number | null;
  conversions: Record<string, number>;
  available: number;
  incoming: number;
  damaged: number;
  low_stock: boolean;
  quarantined: number;
  product_id: string;
  compatibility_status: "unknown" | "specific" | "universal";
}
export interface Line {
  id: string;
  product_id: string;
  quantity: number;
  damaged: number;
  quarantined?: number;
  price_paise: number;
  snapshot: {
    name: string;
    sku: string;
    unit: Unit;
    kind: "goods" | "service";
  };
  outstanding?: number;
  received?: number;
  returned?: number;
}
export interface Movement {
  id: string;
  transaction_id: string;
  product_id: string;
  available_delta: number;
  damaged_delta: number;
  quarantined_delta: number;
  actor: string;
  created_at: string;
}
export interface Transaction {
  id: string;
  kind: "purchase" | "receipt" | "sale" | "return" | "adjustment" | "reversal";
  parent_id: string | null;
  created_at: string;
  actor: string;
  data: Record<string, string | boolean>;
  total_paise: number;
  reversed?: boolean;
  lines: Line[];
  movements: Movement[];
}
export interface ShopState {
  order_reviews?: OrderReview[];
  mode: "demo" | "shop";
  role: "partner" | "staff";
  actor: string;
  transaction_count: number;
  today_sales: { count: number; total_paise: number };
  incoming_transactions: Transaction[];
  incoming_count: number;
  offset: number;
  limit: number;
  products: Product[];
  transactions: Transaction[];
  movements: Movement[];
}
export type Post = (path: string, payload: unknown) => Promise<{ id: string }>;
export interface OrderReview {
  id: string;
  purchase_id?: string | null;
  delivery_status?:
    "not_reached" | "ready_to_count" | "part_received" | "received";
  payload: {
    supplier: string;
    invoice_number: string;
    order_date: string;
    buyer_gstin: string;
    subtotal_paise: number;
    igst_paise: number;
    total_paise: number;
    lines: {
      description: string;
      amount_paise: number;
      quantity_candidate: number | null;
    }[];
    unresolved: string[];
    physical_arrival_confirmed: false;
    stock_posted: false;
  };
}

export interface User {
  id: string;
  username: string;
  role: "partner" | "staff";
  csrf: string;
}
export interface DraftLine {
  product_id?: string;
  purchase_line_id?: string;
  quantity?: number;
  unit?: string;
  cost_paise?: number;
  accepted?: number;
  damaged?: number;
  quarantined?: number;
  description?: string;
  name?: string;
  family_name?: string;
  category?: string;
  amount_paise?: number | null;
  selling_price_paise?: number | null;
  issues?: string[];
}
export interface Draft {
  id: string;
  kind: "purchase" | "receipt" | "intake";
  version: number;
  status: string;
  actor: string;
  payload: {
    supplier?: string;
    invoice_number?: string;
    invoice_date?: string;
    source_file_id?: string;
    purchase_id?: string;
    confirmed?: boolean;
    source_note?: string;
    lines: DraftLine[];
  };
  posted_id?: string;
}
export interface Run {
  clarifications?: { actor: string; message: string; created_at: string }[];
  id: string;
  goal: string;
  status: string;
  requests_used: number;
  tools_used: number;
  error?: string;
  evidence?: {
    summary?: string;
    evidence_ids?: string[];
    unresolved?: string[];
    approvals?: {
      call_id: string;
      tool: string;
      arguments: { draft_id: string; version: number };
    }[];
  };
  steps?: {
    id: string;
    tool: string;
    arguments: unknown;
    result: unknown;
    created_at: string;
  }[];
}
