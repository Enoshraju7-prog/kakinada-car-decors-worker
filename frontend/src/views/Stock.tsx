import { useState } from "react";
import {
  Boxes,
  TriangleAlert,
  Truck,
  ShoppingBag,
  Search,
  X,
  ArrowRight,
  Package,
  Wrench,
  Bot,
} from "@/lib/icons";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { StockStatus } from "@/components/stock-status";
import { OrderedGoods } from "@/components/ordered-goods";
import { money } from "@/lib/api";
import type { ShopState } from "@/lib/types";
import type { View } from "@/lib/navigation";

export default function Stock({
  state,
  navigate,
}: {
  state: ShopState;
  navigate: (view: View) => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("available");
  const goods = state.products.filter((p) => p.kind === "goods");
  const low = goods.filter((p) => p.low_stock);
  const reviews = state.order_reviews ?? [];
  const selected = state.products.filter(
    (p) =>
      [p.name, p.sku, p.model, p.compatibility]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "available" && p.kind === "goods" && p.available > 0) ||
        (filter === "low" && p.low_stock) ||
        (filter === "incoming" && p.incoming > 0)),
  );
  const metrics = [
    {
      label: goods.length ? "Product variants" : "Ordered items",
      value:
        goods.length || reviews.reduce((n, r) => n + r.payload.lines.length, 0),
      note: goods.length
        ? "Individually tracked items"
        : "Awaiting variant verification",
      icon: Boxes,
      action: () => {
        setSearch("");
        setFilter("all");
      },
    },
    {
      label: "Low stock",
      value: low.length,
      note: "At or below your stock limit",
      icon: TriangleAlert,
      action: () => {
        setSearch("");
        setFilter("low");
      },
    },
    {
      label: "Incoming purchases",
      value:
        state.incoming_count +
        reviews.filter((review) => !review.purchase_id).length,
      note: "Awaiting full delivery",
      icon: Truck,
      action: () => navigate("incoming"),
    },
    {
      label: "Sales today",
      value: money(state.today_sales.total_paise),
      note: `${state.today_sales.count} sales · includes credit`,
      icon: ShoppingBag,
      action: () => navigate("history"),
    },
  ];
  return (
    <>
      <div className="stats">
        {metrics.map(({ label, value, note, icon: Icon, action }) => (
          <button type="button" className="stat" key={label} onClick={action}>
            <span className="stat-label">
              {label}
              <Icon aria-hidden="true" />
            </span>
            <strong>{value}</strong>
            <small>{note}</small>
          </button>
        ))}
      </div>
      <OrderedGoods reviews={reviews} onReceive={() => navigate("incoming")} />
      <div className="inventory-summary">
        <div>
          <span className={`status-dot ${low.length ? "attention" : ""}`} />
          <span>
            {low.length
              ? `${low.length} ${low.length === 1 ? "item needs" : "items need"} a stock check.`
              : "No low-stock alerts."}{" "}
            <small>Check exact variants before reordering.</small>
          </span>
        </div>
        {state.role === "partner" ? (
          <Button variant="ghost" onClick={() => navigate("worker")}>
            <Bot aria-hidden="true" />
            Ask the assistant
            <ArrowRight aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <Card className="panel inventory-panel gap-0 py-0">
        <CardHeader className="panel-head">
          <div>
            <CardTitle>Stock on hand</CardTitle>
            <p>Find a product and check what is ready to sell.</p>
          </div>
          <span className="meta">
            {goods.length} goods · {state.products.length - goods.length}{" "}
            services
          </span>
        </CardHeader>
        <div className="tools">
          <div className="search-field">
            <Search aria-hidden="true" />
            <Input
              type="search"
              aria-label="Search products"
              placeholder="Search product, SKU or car model"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search ? (
              <Button
                variant="ghost"
                size="icon"
                aria-label="Clear search"
                onClick={() => setSearch("")}
              >
                <X aria-hidden="true" />
              </Button>
            ) : null}
          </div>
          <NativeSelect
            aria-label="Filter stock status"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <NativeSelectOption value="available">
              Available stock
            </NativeSelectOption>
            <NativeSelectOption value="all">All products</NativeSelectOption>
            <NativeSelectOption value="low">Low stock</NativeSelectOption>
            <NativeSelectOption value="incoming">
              Incoming stock
            </NativeSelectOption>
          </NativeSelect>
        </div>
        <div className="desktop-inventory">
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  "Product",
                  "Available",
                  "Incoming",
                  "Damaged",
                  "On hold",
                  "Price",
                  "Status",
                ].map((label) => (
                  <TableHead key={label}>{label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {selected.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <span className="row-icon">
                      {p.kind === "service" ? (
                        <Wrench aria-hidden="true" />
                      ) : (
                        <Package aria-hidden="true" />
                      )}
                    </span>
                    <strong>{p.name}</strong>
                    <small>
                      {p.sku} · {p.category}
                    </small>
                  </TableCell>
                  <TableCell>
                    <span
                      className={`qty ${p.low_stock ? "low-quantity" : ""}`}
                    >
                      {p.kind === "service" ? "—" : p.available}
                    </span>
                    <small>
                      {p.unit}
                      {p.kind === "goods"
                        ? ` · limit ${p.threshold}`
                        : " · no stock"}
                    </small>
                  </TableCell>
                  <TableCell>{p.kind === "goods" ? p.incoming : "—"}</TableCell>
                  <TableCell>{p.kind === "goods" ? p.damaged : "—"}</TableCell>
                  <TableCell>
                    {p.kind === "goods" ? p.quarantined : "—"}
                  </TableCell>
                  <TableCell className="price-cell">
                    {money(p.price_paise)}
                    {state.role === "partner" ? (
                      <small>
                        Buy:{" "}
                        {p.purchase_price_paise == null
                          ? "Unconfirmed"
                          : money(p.purchase_price_paise)}
                      </small>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StockStatus product={p} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="mobile-inventory">
          {selected.map((p) => (
            <article className="inventory-item" key={p.id}>
              <div className="inventory-item-title">
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {p.sku} · {p.category}
                  </small>
                </div>
                <StockStatus product={p} />
              </div>
              <div className="inventory-item-values">
                <div>
                  <small>Available</small>
                  <strong className={p.low_stock ? "low-quantity" : ""}>
                    {p.kind === "service" ? "—" : p.available}{" "}
                    <span>{p.unit}</span>
                  </strong>
                </div>
                <div>
                  <small>Incoming</small>
                  <strong>{p.kind === "service" ? "—" : p.incoming}</strong>
                </div>
                <div>
                  <small>Selling price</small>
                  <strong>{money(p.price_paise)}</strong>
                  {state.role === "partner" ? (
                    <small>
                      Buy:{" "}
                      {p.purchase_price_paise == null
                        ? "Unconfirmed"
                        : money(p.purchase_price_paise)}
                    </small>
                  ) : null}
                </div>
              </div>
              {p.kind === "goods" && (p.damaged > 0 || p.quarantined > 0) ? (
                <div className="inventory-item-note">
                  Damaged: {p.damaged} · On hold: {p.quarantined}
                </div>
              ) : null}
            </article>
          ))}
        </div>
        {!selected.length ? (
          <div className="empty">
            <Boxes aria-hidden="true" />
            <h3>
              {state.products.length
                ? "No matching products"
                : "Start with your first product"}
            </h3>
            <p>
              {state.products.length
                ? "Try another name, SKU or stock filter."
                : "Add an exact variant and its unit to begin tracking stock."}
            </p>
            {state.products.length ? (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch("");
                  setFilter("all");
                }}
              >
                Clear filters
              </Button>
            ) : state.role === "partner" ? (
              <Button onClick={() => navigate("catalogue")}>
                Add a product
              </Button>
            ) : null}
          </div>
        ) : null}
        <div className="hint">
          <span>
            {selected.length} {selected.length === 1 ? "product" : "products"}{" "}
            shown
          </span>
          <span>
            Only accepted deliveries are available to sell. On hold =
            quarantined.
          </span>
        </div>
      </Card>
    </>
  );
}
