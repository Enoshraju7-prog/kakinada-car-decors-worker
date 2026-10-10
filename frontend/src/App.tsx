import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  readState,
  postVerified,
  restoreSession,
  signIn,
  api,
  setSession,
} from "@/lib/api";
import type { ShopState, User } from "@/lib/types";
import Stock from "@/views/Stock";
import { ThemeSwitch } from "@/components/theme-switch";
import { PartnerAlerts } from "@/components/partner-alerts";
import automotiveCabin from "@/assets/automotive-cabin.jpg";
import automotiveCabinLight from "@/assets/automotive-cabin-light.jpg";
import Incoming from "@/views/Incoming";
import Sale from "@/views/Sale";
import History from "@/views/History";
import Catalogue from "@/views/Catalogue";
import Approvals from "@/views/Approvals";
import Worker from "@/views/Worker";
import Corrections from "@/views/Corrections";
import { Input } from "@/components/ui/input";
import { Panel, Field } from "@/components/shop-form";
import { Brand, WorkspaceNavigation } from "@/components/workspace-navigation";
import { views, type View } from "@/lib/navigation";
import {
  ShoppingBag,
  PackageCheck,
  RefreshCw,
  LogOut,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
} from "@/lib/icons";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [view, setView] = useState<View>("stock");
  const [state, setState] = useState<ShopState | null>(null);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  useEffect(() => {
    let active = true;
    restoreSession()
      .then((u) => {
        if (active) setUser(u);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setSessionReady(true);
      });
    const expired = () => {
      setUser(null);
      setState(null);
    };
    window.addEventListener("kcd-session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("kcd-session-expired", expired);
    };
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    readState()
      .then((s) => {
        if (active) setState(s);
      })
      .catch((e) => {
        if (active) setNotice({ text: e.message, error: true });
      });
    return () => {
      active = false;
    };
  }, [user]);
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    const data = new FormData(event.currentTarget);
    try {
      setUser(
        await signIn(
          String(data.get("username")),
          String(data.get("password")),
        ),
      );
      setView("stock");
      setNotice(null);
    } catch (e) {
      setLoginError((e as Error).message);
    } finally {
      setLoginBusy(false);
    }
  }
  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
      setSession(null);
      setUser(null);
      setState(null);
    } catch (e) {
      setNotice({ text: (e as Error).message, error: true });
    }
  }
  const changeView = (next: View) => {
    setView(next);
    window.scrollTo({ top: 0 });
    setNotice(null);
  };
  async function refresh(offset = 0) {
    try {
      setState(await readState(offset));
    } catch (e) {
      setNotice({ text: (e as Error).message, error: true });
    }
  }
  async function post(path: string, payload: unknown) {
    try {
      const result = await postVerified(path, payload);
      setState(result.state);
      setNotice({
        text: "Saved successfully. You can check it in Activity.",
        error: false,
      });
      return result;
    } catch (e) {
      const uncertain =
        !(e instanceof ApiError) || !e.status || e.status >= 500;
      const message = `${(e as Error).message}${uncertain ? " Saving is unconfirmed. Retry with the same details to avoid a duplicate." : ""}`;
      setNotice({ text: message, error: true });
      throw new Error(message);
    }
  }
  if (!sessionReady)
    return <div className="login-shell">Opening workspace…</div>;
  if (!user)
    return (
      <div className="login-shell">
        <section
          className="welcome-visual"
          aria-label="Kakinada Car Decors welcome"
        >
          <img className="welcome-dark" src={automotiveCabin} alt="" />
          <img className="welcome-light" src={automotiveCabinLight} alt="" />
          <div className="welcome-copy">
            <span className="eyebrow">KAKINADA CAR DECORS</span>
            <h2>
              Every detail.
              <br />
              Under control.
            </h2>
            <p>Your stock. Your sales. Your next move.</p>
          </div>
          <span className="welcome-caption">THE SHOP WORKSPACE</span>
        </section>
        <div className="login-card">
          <div className="login-theme">
            <ThemeSwitch />
          </div>
          <Brand />
          <div className="eyebrow">YOUR SHOP, IN ONE PLACE</div>
          <h1>Welcome back.</h1>
          <p>Stock, sales and the next step. All in your shop workspace.</p>
          <Panel title="Sign in" note="Secure workspace">
            <form onSubmit={(e) => void login(e)}>
              <fieldset disabled={loginBusy}>
                <Field label="Username">
                  <Input name="username" autoComplete="username" required />
                </Field>
                <Field label="Password">
                  <Input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </Field>
                {loginError ? (
                  <div className="form-error" role="alert">
                    {loginError}
                  </div>
                ) : null}
                <div className="actions">
                  <Button type="submit" className="login-submit">
                    {loginBusy ? "Signing in…" : "Sign in to workspace"}{" "}
                    <ArrowRight aria-hidden="true" />
                  </Button>
                </div>
              </fieldset>
            </form>
          </Panel>
        </div>
      </div>
    );
  return (
    <>
      <WorkspaceNavigation user={user} view={view} onChange={changeView} />
      <div className="main-shell">
        <header className="topbar">
          <span className="environment-label">
            {state
              ? state.mode === "demo"
                ? "Demo workspace · Synthetic data"
                : "Private shop · Partner workspace"
              : "Loading workspace…"}
          </span>
          <div>
            <ThemeSwitch />
            {user.role === "partner" ? <PartnerAlerts /> : null}
            <span className="account-label">
              {user.username} · {user.role}
            </span>
            <Button
              variant="ghost"
              aria-label="Sign out"
              onClick={() => void logout()}
            >
              <LogOut aria-hidden="true" />
              <span className="button-label">Sign out</span>
            </Button>
            <span className="workspace-date">
              {new Date().toLocaleDateString("en-IN", {
                timeZone: "Asia/Kolkata",
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
            <Button
              variant="outline"
              className="quiet"
              aria-label="Refresh workspace"
              onClick={() => void refresh()}
            >
              <RefreshCw aria-hidden="true" />
              <span className="button-label">Refresh</span>
            </Button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {view === "worker" ? "YOUR SHOP ASSISTANT" : "SHOP WORKSPACE"}
              </div>
              <h1>{views[view][1]}</h1>
              <p>{views[view][2]}</p>
            </div>
            {view !== "sale" && view !== "worker" ? (
              <div className="heading-actions">
                {view !== "incoming" ? (
                  <Button
                    variant="outline"
                    onClick={() => changeView("incoming")}
                  >
                    <PackageCheck aria-hidden="true" />
                    Receive stock
                  </Button>
                ) : null}
                <Button onClick={() => changeView("sale")}>
                  <ShoppingBag aria-hidden="true" />
                  Make sale
                </Button>
              </div>
            ) : null}
          </div>
          {notice ? (
            <div
              id="notice"
              role={notice.error ? "alert" : "status"}
              aria-live="polite"
              className={notice.error ? "error" : ""}
            >
              {notice.error ? (
                <AlertCircle aria-hidden="true" />
              ) : (
                <CheckCircle2 aria-hidden="true" />
              )}
              <span>{notice.text}</span>
            </div>
          ) : null}
          {state ? (
            <>
              {view === "stock" ? (
                <Stock state={state} navigate={changeView} />
              ) : null}
              {view === "incoming" ? (
                <Incoming
                  products={state.products}
                  transactions={state.incoming_transactions}
                  total={state.incoming_count}
                  reviews={state.order_reviews ?? []}
                  role={user.role}
                  post={post}
                  openApprovals={() => changeView("approvals")}
                  openAssistant={() => changeView("worker")}
                />
              ) : null}
              {view === "sale" ? (
                <Sale
                  products={state.products}
                  post={post}
                  partner={user.role === "partner"}
                />
              ) : null}
              {view === "history" ? (
                <History
                  transactions={state.transactions}
                  movementCount={state.movements.length}
                  partner={user.role === "partner"}
                  post={post}
                />
              ) : null}
              {view === "history" ? (
                <div className="pagination">
                  <Button
                    variant="outline"
                    disabled={!state.offset}
                    onClick={() =>
                      void refresh(Math.max(0, state.offset - state.limit))
                    }
                  >
                    Previous
                  </Button>
                  <span>
                    {state.offset + 1}–
                    {state.offset + state.transactions.length} of{" "}
                    {state.transaction_count}
                  </span>
                  <Button
                    variant="outline"
                    disabled={
                      state.offset + state.limit >= state.transaction_count
                    }
                    onClick={() => void refresh(state.offset + state.limit)}
                  >
                    Next
                  </Button>
                </div>
              ) : null}
              {view === "approvals" ? (
                <Approvals state={state} refresh={refresh} />
              ) : null}
              {view === "worker" ? (
                <Worker state={state} refresh={refresh} />
              ) : null}
              {view === "corrections" ? (
                <Corrections products={state.products} post={post} />
              ) : null}
              {view === "catalogue" ? (
                <Catalogue post={post} products={state.products} />
              ) : null}
            </>
          ) : (
            <div className="panel empty">
              {notice?.error
                ? "Could not load your shop records. Use Refresh to try again."
                : "Loading your shop records…"}
            </div>
          )}
          <footer>
            Local inventory pilot · Counter records are not tax invoices ·
            Billing configuration pending
          </footer>
        </main>
      </div>
    </>
  );
}
