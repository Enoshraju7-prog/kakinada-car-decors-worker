import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, Field, Confirmation } from "@/components/shop-form";
import { api, write, time, postVerified } from "@/lib/api";
import type { Run, ShopState, Draft } from "@/lib/types";
import { DraftReview } from "./Approvals";
import IntakeReview from "@/components/intake-review";
import {
  Bot,
  CheckCircle2,
  CirclePause,
  CircleAlert,
  Clock,
} from "@/lib/icons";

import { SalesHistoryReport } from "@/components/sales-history-report";

const AssistantReport = lazy(() => import("@/components/assistant-report"));

const statusLabels: Record<string, string> = {
  pending: "Queued",
  running: "Working",
  complete: "Completed & verified",
  waiting_approval: "Needs your approval",
  needs_clarification: "Needs more details",
  failed: "Stopped — review needed",
};
const toolLabels: Record<string, string> = {
  find_documents: "Find the attached bill",
  extract_document: "Read the bill",
  lookup_catalogue: "Find matching products",
  lookup_families: "Check saved product families",
  prepare_intake: "Prepare items, families and buying rates",
  check_bill: "Check for an existing bill",
  find_purchase_drafts: "Find an existing draft",
  read_draft: "Check the saved draft",
  prepare_purchase: "Prepare a purchase draft",
  prepare_receipt: "Prepare delivery counts",
  post_approved_draft: "Save the approved draft",
  verify_transaction: "Verify saved records",
  query_inventory: "Check current stock",
  save_sales_report: "Find sales by date and save the report",
  save_shortage_report: "Save the low-stock report",
  read_report: "Verify the saved report",
  query_order_reviews: "Review ordered goods",
  save_arrival_checklist: "Save the delivery checklist",
};
export default function Worker({
  state,
  refresh,
}: {
  state: ShopState;
  refresh: () => Promise<void>;
}) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load(id = selected?.id) {
    const list = await api<Run[]>("/api/agent/runs");
    setRuns(list);
    if (id) {
      const run = await api<Run>(`/api/agent/runs/${id}`);
      if (
        JSON.stringify(run.evidence?.approvals) !==
        JSON.stringify(selected?.evidence?.approvals)
      )
        setConfirmed(false);
      setSelected(run);
      if (run.status === "complete" && selected?.status !== "complete")
        await refresh();
      // A proposal needing prices/details is useful before a posting approval exists.
      const ids = new Set(
        (run.evidence?.approvals ?? []).map((a) => a.arguments.draft_id),
      );
      for (const step of run.steps ?? []) {
        if (
          ["prepare_intake", "prepare_purchase", "read_draft"].includes(
            step.tool,
          )
        ) {
          const result = step.result as { id?: string; error?: string };
          if (result?.id && !result.error) ids.add(result.id);
        }
      }
      const previews = await Promise.all(
        [...ids].map((id) => api<Draft>(`/api/drafts/${id}`)),
      );
      setDrafts(previews.filter((d) => d.status !== "posted"));
    }
  }
  useEffect(() => {
    let active = true;
    api<Run[]>("/api/agent/runs")
      .then((x) => {
        if (active) setRuns(x);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!selected || !["pending", "running"].includes(selected.status)) return;
    const timer = setTimeout(() => {
      void load(selected.id).catch((e) => setError(e.message));
    }, 3000);
    return () => clearTimeout(timer);
  }, [selected]);
  async function clarify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setConfirmed(false);
    setBusy(true);
    setError("");
    try {
      await postVerified(`/api/agent/runs/${selected.id}/clarify`, {
        message: String(data.get("message")),
      });
      await load(selected.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setConfirmed(false);
    try {
      const file = data.get("file");
      if (
        !(file instanceof File && file.size) &&
        !String(data.get("goal") ?? "").trim()
      )
        throw new Error("Attach a bill or type the task you want help with.");
      const attachments: string[] = [];
      if (file instanceof File && file.size) {
        const upload = new FormData();
        upload.append("file", file);
        attachments.push(
          (
            await api<{ id: string }>("/api/files", {
              method: "POST",
              body: upload,
            })
          ).id,
        );
      }
      const run = await postVerified("/api/agent/runs", {
        goal:
          String(data.get("goal") ?? "").trim() ||
          "Read the attached supplier bill. Check duplicates and existing parts, prepare editable item and family proposals, read the draft back, and tell me what needs review. Do not receive goods or set selling prices.",
        attachments,
      });
      await load(run.id);
      form.reset();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resume() {
    if (!selected || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      await write(`/api/agent/runs/${selected.id}/resume`, {});
      setConfirmed(false);
      await load(selected.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Panel
        title="What can I help with?"
        note="Bills, product matching and stock checks"
      >
        <form onSubmit={(e) => void start(e)}>
          <fieldset disabled={busy}>
            <Field label="Describe your task">
              <textarea
                name="goal"
                maxLength={2000}
                rows={3}
                placeholder="Upload a bill below, or type what you bought with quantities, units and buying rates. You can also ask for a low-stock report."
              />
            </Field>
            <Field label="Optional supplier bill (PDF, PNG or JPEG, up to 4 MiB)">
              <Input
                type="file"
                name="file"
                accept="application/pdf,image/png,image/jpeg"
              />
            </Field>
            <div className="actions">
              <span className="meta">
                Manual stock and sales continue if AI is unavailable.
              </span>
              <Button type="submit">
                <Bot aria-hidden="true" />
                {busy ? "Starting…" : "Start task"}
              </Button>
            </div>
          </fieldset>
        </form>
      </Panel>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="section-top">
        <h2>Recent tasks</h2>
        <Button
          variant="outline"
          onClick={() => void load().catch((e) => setError(e.message))}
        >
          Refresh tasks
        </Button>
      </div>
      <div className="run-list">
        {runs.map((r) => (
          <Button
            variant="outline"
            key={r.id}
            aria-pressed={selected?.id === r.id}
            onClick={() => {
              setConfirmed(false);
              void load(r.id).catch((e) => setError(e.message));
            }}
          >
            {r.status === "complete" ? (
              <CheckCircle2 aria-hidden="true" />
            ) : r.status === "waiting_approval" ? (
              <CirclePause aria-hidden="true" />
            ) : r.status === "failed" || r.status === "needs_clarification" ? (
              <CircleAlert aria-hidden="true" />
            ) : (
              <Clock aria-hidden="true" />
            )}
            <span className="run-title">
              <strong>
                {statusLabels[r.status] ?? r.status.replaceAll("_", " ")}
              </strong>
              <small>{r.goal}</small>
            </span>
          </Button>
        ))}
      </div>
      {selected ? (
        <>
          <Panel
            title={
              statusLabels[selected.status] ??
              selected.status.replaceAll("_", " ")
            }
            note={`${selected.requests_used}/10 request slots · ${selected.tools_used}/20 tools`}
          >
            <p>{selected.goal}</p>
            <small>Run: {selected.id}</small>
            {selected.clarifications?.map((note, i) => (
              <p key={i}>
                <strong>{note.actor}:</strong> {note.message}
              </p>
            ))}
            {selected.error ? (
              <p className="form-error">{selected.error}</p>
            ) : null}
            {selected.evidence?.summary ? (
              <Suspense fallback={<p>Formatting the saved report…</p>}>
                <AssistantReport text={selected.evidence.summary} />
              </Suspense>
            ) : null}
            {(selected.steps ?? [])
              .filter((step) => step.tool === "read_report")
              .map((step) => (
                <SalesHistoryReport key={step.id} result={step.result} />
              ))}
            {selected.evidence?.unresolved?.map((q, i) => (
              <p key={i} className="form-error">
                Needs clarification: {q}
              </p>
            ))}
            {selected.evidence?.evidence_ids?.map((id) => (
              <div key={id}>
                <code>{id}</code>
              </div>
            ))}
            {(selected.steps ?? []).map((step, index) => (
              <details key={step.id}>
                <summary>
                  {index + 1}. {toolLabels[step.tool] ?? step.tool}{" "}
                  <small>{time(step.created_at)}</small>
                </summary>
                <div className="history-detail">
                  <strong>Technical input · {step.tool}</strong>
                  <pre>{JSON.stringify(step.arguments, null, 2)}</pre>
                  <strong>Observed result</strong>
                  <pre>{JSON.stringify(step.result, null, 2)}</pre>
                </div>
              </details>
            ))}
          </Panel>
          {drafts.map((d) =>
            d.kind === "intake" ? (
              <IntakeReview
                key={`${d.id}:${d.version}`}
                draft={d}
                state={state}
                postable={selected.status !== "waiting_approval"}
                changed={async () => {
                  setConfirmed(false);
                  await load(selected.id);
                  await refresh();
                }}
              />
            ) : (
              <DraftReview
                key={`${d.id}:${d.version}`}
                draft={d}
                state={state}
                postable={false}
                changed={async () => {
                  setConfirmed(false);
                  await load(selected.id);
                }}
              />
            ),
          )}
          {["needs_clarification", "waiting_approval", "failed"].includes(
            selected.status,
          ) ? (
            <Panel
              title="Help the assistant continue"
              note="Remaining execution budget is preserved"
            >
              <form onSubmit={(e) => void clarify(e)}>
                <Field label="Confirmed details or correction">
                  <textarea
                    name="message"
                    required
                    maxLength={2000}
                    rows={3}
                    placeholder="Specify the exact SKU, confirmed unit or corrected draft version."
                  />
                </Field>
                <div className="actions">
                  <Button
                    type="submit"
                    disabled={
                      busy ||
                      selected.requests_used >= 10 ||
                      selected.tools_used >= 20
                    }
                  >
                    Continue with these details
                  </Button>
                </div>
              </form>
            </Panel>
          ) : null}
          {selected.status === "waiting_approval" ? (
            <Panel
              title="Partner checkpoint"
              note="Approval applies only to the versions requested above"
            >
              <Confirmation
                checked={confirmed}
                onChange={setConfirmed}
                label="I reviewed every draft above, confirmed quantities/units and any physical receipt evidence, and authorize these exact versions."
              />
              <div className="actions">
                <Button
                  disabled={!confirmed || busy}
                  onClick={() => void resume()}
                >
                  Approve drafts & resume worker
                </Button>
              </div>
            </Panel>
          ) : null}
        </>
      ) : (
        <div className="panel empty">
          {runs.length
            ? "Choose a task to see what the assistant did and what it saved."
            : "Your first task starts above. Try asking for a low-stock report, or attach a generated supplier bill for review."}
        </div>
      )}
    </>
  );
}
