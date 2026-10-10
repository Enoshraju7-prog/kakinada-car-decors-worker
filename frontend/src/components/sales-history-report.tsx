import { money, time } from "@/lib/api";
import { SaleCustomer } from "@/components/customer-details";

type Sale = {
  order_id: string;
  receipt_number: string;
  purchased_at_ist: string;
  customer_reference: string | null;
  customer_type: string;
  status: string;
  payment: string;
  total_paise: number;
  items: {
    name: string;
    sku: string;
    quantity: number;
    unit: string;
    returned_quantity: number;
  }[];
};
type Report = {
  kind: "sales_history";
  start_date: string;
  end_date: string;
  sale_count: number;
  void_count: number;
  recorded_sales_total_paise: number;
  credit_sales_total_paise: number;
  has_more: boolean;
  next_offset: number | null;
  offset: number;
  totals_note: string;
  sales: Sale[];
};

export function SalesHistoryReport({ result }: { result: unknown }) {
  if (!result || typeof result !== "object" || !("data" in result)) return null;
  const value = result.data;
  if (
    !value ||
    typeof value !== "object" ||
    !("kind" in value) ||
    value.kind !== "sales_history"
  )
    return null;
  const report = value as Report;
  return (
    <section aria-label="Saved sales history" className="form-lines">
      <h3>
        Sales: {report.start_date} to {report.end_date} · IST
      </h3>
      <p>
        {report.sale_count} sales · {report.void_count} void · Recorded total{" "}
        {money(report.recorded_sales_total_paise)} · Credit{" "}
        {money(report.credit_sales_total_paise)}
      </p>
      <p className="meta">{report.totals_note}</p>
      {report.sales.length === 0 ? (
        <p>No sales in this range.</p>
      ) : (
        <div
          className="report-table"
          tabIndex={0}
          aria-label="Sales history table"
        >
          <table>
            <thead>
              <tr>
                <th>Date / order</th>
                <th>Products purchased</th>
                <th>Customer</th>
                <th>Total / payment</th>
              </tr>
            </thead>
            <tbody>
              {report.sales.map((sale) => (
                <tr key={sale.order_id}>
                  <td>
                    {time(sale.purchased_at_ist)}
                    <p>{sale.receipt_number}</p>
                    <small>Order: {sale.order_id}</small>
                    {sale.status === "VOID" && (
                      <p>
                        <strong>VOID</strong>
                      </p>
                    )}
                  </td>
                  <td>
                    {sale.items.map((item, index) => (
                      <p key={`${item.sku}-${index}`}>
                        {item.name} · {item.quantity} {item.unit}
                        {item.returned_quantity > 0 &&
                          ` · ${item.returned_quantity} returned`}
                        <br />
                        <small>{item.sku}</small>
                      </p>
                    ))}
                  </td>
                  <td>
                    {sale.customer_reference ? (
                      <SaleCustomer saleId={sale.order_id} />
                    ) : (
                      sale.customer_type
                    )}
                  </td>
                  <td>
                    {money(sale.total_paise)}
                    <p>
                      {sale.payment === "credit"
                        ? "Credit · Unpaid"
                        : sale.payment.toUpperCase()}
                    </p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="meta">
        Showing {report.offset + (report.sales.length ? 1 : 0)}–
        {report.offset + report.sales.length} of {report.sale_count}. Customer
        details open privately and are not sent to the assistant.
      </p>
      {report.has_more && (
        <p>
          More sales remain. Ask the assistant to continue this date range from
          offset {report.next_offset}.
        </p>
      )}
    </section>
  );
}
