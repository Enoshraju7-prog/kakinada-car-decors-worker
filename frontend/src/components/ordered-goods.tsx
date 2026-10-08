import { Panel } from "@/components/shop-form";
import { money } from "@/lib/api";
import type { OrderReview } from "@/lib/types";
import { Button } from "@/components/ui/button";

function nextActionLabel(review: OrderReview) {
  if (!review.purchase_id) return "1 · Confirm bill items";
  if (review.delivery_status === "part_received")
    return "2 · Count remaining delivery";
  return "2 · Count this delivery";
}

export function OrderedGoods({
  reviews,
  onReceive,
  onApprove,
}: {
  reviews: OrderReview[];
  onReceive?: (review: OrderReview) => void;
  onApprove?: () => void;
}) {
  if (!reviews.length) return null;
  return (
    <Panel
      title="Orders & deliveries"
      note="Physical verification needed in Kakinada"
    >
      <p>
        Follow Confirm bill → Count → Approve → Ready to sell. Use the next
        action on each order. Only approved accepted counts become available.
      </p>
      <div className="ordered-bills">
        {reviews.map((review) => {
          const { id, payload: p } = review;
          return (
            <article key={id} className="ordered-bill">
              <div className="card-title">
                <div>
                  <h3>{p.supplier}</h3>
                  <p>
                    Bill {p.invoice_number} · Order date {p.order_date}
                  </p>
                </div>
                <span
                  className={`badge ${review.delivery_status === "received" ? "available" : "low"}`}
                >
                  {review.delivery_status === "received"
                    ? "Ready to sell"
                    : review.delivery_status === "part_received"
                      ? "Part received"
                      : review.delivery_status === "ready_to_count"
                        ? "Ready to count"
                        : "Bill not confirmed"}
                </span>
              </div>
              {p.lines.map((l, i) => (
                <div className="ordered-line" key={i}>
                  <div>
                    <strong>{l.description}</strong>
                    <small>
                      {l.quantity_candidate == null
                        ? "Quantity pending"
                        : `Quantity candidate: ${l.quantity_candidate}`}{" "}
                      · unit & exact variant to confirm
                    </small>
                  </div>
                  <div className="price-cell">
                    <strong>{money(l.amount_paise)}</strong>
                    <small>Purchase amount</small>
                  </div>
                </div>
              ))}
              <div className="order-total">
                <span>
                  Goods {money(p.subtotal_paise)} · IGST {money(p.igst_paise)}
                </span>
                <strong>Total {money(p.total_paise)}</strong>
              </div>
              <p className="meta">
                {review.delivery_status === "received"
                  ? "Delivery counted and approved. Accepted items can now be sold."
                  : review.delivery_status === "part_received"
                    ? "Some goods are received. Count the remaining delivery when it arrives."
                    : review.purchase_id
                      ? "Next: count accepted, damaged and on-hold items, then approve."
                      : "Next: confirm exact items and units on the bill."}
              </p>
              <details className="optional-fields">
                <summary>What needs checking</summary>
                <ul>
                  {p.unresolved.map((u) => (
                    <li key={u}>{u}</li>
                  ))}
                </ul>
                <p>
                  Amounts confirmed by partner; extraction is evidence for
                  review. Only accepted physical counts become available after
                  approval.
                </p>
              </details>
              <div className="receiving-options">
                {onReceive && review.delivery_status !== "received" ? (
                  <Button variant="outline" onClick={() => onReceive(review)}>
                    {nextActionLabel(review)}
                  </Button>
                ) : null}
                {onApprove &&
                review.purchase_id &&
                review.delivery_status !== "received" ? (
                  <Button variant="outline" onClick={onApprove}>
                    3 · Go to approvals
                  </Button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </Panel>
  );
}
