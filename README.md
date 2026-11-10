# Droguería Starling

Product catalog with an integrated point of sale (POS) for medicine retail stores.
Vue 3 + FastAPI + PostgreSQL. Architecture: [docs/architecture.png](docs/architecture.png).
Business rules: [docs/business-rules.csv](docs/business-rules.csv).
Assumptions and conventions: [CLAUDE.md](CLAUDE.md).

## What it does

- **POS**: barcode-first, keyboard-driven checkout (F2 scan, F9 charge, Esc new sale),
  register shifts with cash closing, split payments with change, 80 mm receipts.
- **Pharmacy rules**: lots with expiry dates, FEFO picking, no expired or negative stock,
  prescription capture (JPG/PNG/PDF) for Rx products, extra checks and pharmacist
  approval for controlled products.
- **Corrections**: same-shift voids and partial returns as separate documents; completed
  sales are immutable.
- **Back office**: catalog with active ingredients, inventory adjustments and write-offs,
  purchasing with goods receipt, customers, reports (daily sales, expiring lots, low
  stock, stock valuation), daily alerts, and an audit log of every change.

When a cashier needs authorization (large discount, controlled drug, lot override, void,
Rx return) the UI shows a dialog where a pharmacist or admin enters their credentials;
the action is then retried with a short-lived approval token.

## Prerequisites

- Docker Desktop
- The existing Postgres container `order-management-db` (see [CLAUDE.md](CLAUDE.md#database-existing-docker-container))
  with the `drogueria_app` role and the `drogueria_starling` / `drogueria_starling_test` databases
- For local development: [uv](https://docs.astral.sh/uv/) and Node.js **20.19+**

Copy `.env.example` to `.env` and fill in the password and `JWT_SECRET`.

## Run with Docker Compose

```bash
docker compose up -d --build
```

The app is served at <http://localhost:8081> (API docs at `/api/v1/docs`). The API container
applies migrations on start and joins the `database_default` network to reach Postgres.
Compose serves plain HTTP; in production put it behind a TLS-terminating proxy or add
certificates to `frontend/nginx.conf`.

Create the first admin (the password is prompted, never passed as an argument):

```bash
docker compose exec api python -m app.cli create-admin --username admin --full-name "Store Admin"
```

Then, as admin: create a register (Admin → Cajas), users, products, and load opening
stock per lot (Inventario → Existencia inicial) or receive a purchase order.

## Local development

Backend (from `backend/`):

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.cli create-admin --username admin --full-name "Store Admin"
uv run uvicorn app.main:app --reload
```

Frontend (from `frontend/`; the dev server proxies `/api` to `localhost:8000`):

```bash
npm install
npm run dev
```

## Checks

Backend (from `backend/`; tests run against `TEST_DATABASE_URL`):

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Frontend (from `frontend/`):

```bash
npm test && npm run type-check && npm run lint && npm run build
```

Every rule in [docs/business-rules.csv](docs/business-rules.csv) has at least one backend test
named after its code, e.g. `test_inv1_…` for INV-1 or `test_sal7_…` for SAL-7.

## Project layout

```
backend/   FastAPI app: api/v1 (routers) → services (business rules) → repositories/models
           alembic/ migrations, tests/ (pytest against PostgreSQL)
frontend/  Vue 3 SPA: views, stores (Pinia), services (Axios), i18n (es/en)
docs/      architecture diagram
```
