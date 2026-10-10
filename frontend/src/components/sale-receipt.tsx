import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { setSession } from "@/lib/api";

export function SaleReceipt({ saleId }: { saleId: string }) {
  const [paper, setPaper] = useState("a4");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function open(action: "view" | "download" | "print") {
    // Open synchronously so the user's click is not lost to popup blocking.
    const popup =
      action === "download" ? null : window.open("about:blank", "_blank");
    if (action !== "download" && !popup) {
      setError(
        "Allow a new tab to view or print the bill, or choose Download PDF.",
      );
      return;
    }
    if (popup) popup.opener = null;
    setBusy(true);
    setError("");
    let objectUrl: string | undefined;
    try {
      const path = `/api/sales/${saleId}/receipt${action === "print" ? "/print" : ".pdf"}?format=${paper}`;
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          window.dispatchEvent(new Event("kcd-session-expired"));
        }
        const body = await response.json();
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Bill could not be opened.",
        );
      }
      if (action === "print") {
        // Dedicated page opens the real browser print dialog, using no inline script.
        popup!.location.replace(path);
      } else {
        if (
          !response.headers.get("content-type")?.startsWith("application/pdf")
        )
          throw new Error("The server did not return a PDF.");
        objectUrl = URL.createObjectURL(await response.blob());
        if (action === "view") popup!.location.replace(objectUrl);
        else {
          const link = document.createElement("a");
          link.href = objectUrl;
          link.download =
            response.headers
              .get("content-disposition")
              ?.match(/filename="([^"]+)"/)?.[1] ?? `KCD-receipt-${paper}.pdf`;
          link.click();
        }
        const url = objectUrl;
        window.setTimeout(
          () => URL.revokeObjectURL(url),
          action === "download" ? 60000 : 600000,
        );
      }
    } catch (e) {
      popup?.close();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setError(`Sale saved - retry bill. ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Sales receipt" className="form-lines">
      <div className="actions">
        <NativeSelect
          aria-label="Receipt paper size"
          value={paper}
          disabled={busy}
          onChange={(e) => setPaper(e.target.value)}
        >
          <NativeSelectOption value="a4">A4 bill</NativeSelectOption>
          <NativeSelectOption value="80mm">80 mm receipt</NativeSelectOption>
        </NativeSelect>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => void open("view")}
        >
          View bill
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => void open("download")}
        >
          Download PDF
        </Button>
        <Button
          type="button"
          disabled={busy}
          onClick={() => void open("print")}
        >
          Print
        </Button>
      </div>
      <p className="meta">
        Sales receipt - Not a GST tax invoice. Printing does not change stock.
      </p>
      {busy ? <p role="status">Opening bill…</p> : null}
      {error ? (
        <p role="alert" className="form-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}
