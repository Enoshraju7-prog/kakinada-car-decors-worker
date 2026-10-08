# React frontend

React + TypeScript + Vite + Tailwind + shadcn/ui/Radix. Exact dependency versions are pinned in package.json and package-lock.json. Generated components retain the license in THIRD_PARTY_NOTICES.md.

From this directory: `npm ci --ignore-scripts`, then `npm run build`. The root `dev.sh` builds and serves the production UI with FastAPI. `npm run dev` provides hot reload and proxies `/api` to the running backend.

Product views live in `src/views`: stock search/shortages, supplier bill/physical receipt, multi-line sale with review dialog, linked returns/history, and exact product creation. `src/lib/api.ts` converts decimal text to paise, handles errors, preserves hashed request keys for uncertain retries, and verifies saved transaction/product readback. The UI has no independent inventory ledger or offline checkout.

TanStack Virtual is reserved for large catalogues; current lists render normally. `npm run typecheck` and `npm run format:check` verify types/formatting. Browser flows were exercised against actual saved demo state; see ../docs/VERIFICATION.md.
