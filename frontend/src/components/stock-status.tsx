import { Badge } from "@/components/ui/badge";
import type { Product } from "@/lib/types";

export function StockStatus({ product }: { product: Product }) {
  const status =
    product.kind === "service"
      ? "service"
      : product.available === 0
        ? "out"
        : product.low_stock
          ? "low"
          : "ready";
  return (
    <Badge className={`badge ${status}`}>
      {status === "service"
        ? "Service"
        : status === "out"
          ? "Out of stock"
          : status === "low"
            ? "Low stock"
            : "Ready to sell"}
    </Badge>
  );
}
