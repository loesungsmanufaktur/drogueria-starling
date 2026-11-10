# Drogueria Starling — Project Context

Product catalog with an integrated point of sale (POS) for medicine retail stores (droguerías).
Architecture diagram: [docs/architecture.png](docs/architecture.png) (source: `docs/architecture.svg`).

## Stack

| Layer     | Choice                                                                 |
|-----------|------------------------------------------------------------------------|
| Frontend  | Vue 3 + Vite + TypeScript, Vue Router, Pinia, Axios, Vitest            |
| Backend   | FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 (async), Alembic, pytest |
| Database  | PostgreSQL 18 — **existing Docker container owned by the user** (see below) |
| Edge      | Nginx (serves the Vue build, proxies `/api/*` to FastAPI)              |
| Packaging | Docker Compose for `web` and `api`; DB is external to this compose file |

## Repository layout (target)

```
backend/
  app/
    api/v1/          # routers only: parse request, call service, return schema
    core/            # settings (pydantic-settings), security, logging
    db/              # engine, session, base model
    models/          # SQLAlchemy models
    schemas/         # Pydantic request/response models
    services/        # business logic — all business rules live here
    repositories/    # data access, no business logic
    jobs/            # scheduled tasks (expiry / low-stock alerts)
  alembic/
  tests/
frontend/
  src/{views,components,stores,services,router,i18n}
docs/
docker-compose.yml
.env.example
```

## Database (existing Docker container)

- Postgres already runs in a Docker container managed by the user. **Do not create, recreate, or
  remove that container or its volume**, and do not add a `db` service to `docker-compose.yml`.

  | Property        | Value                                                                 |
  |-----------------|-----------------------------------------------------------------------|
  | Container       | `order-management-db`                                                 |
  | Image           | `postgres:18.3`                                                       |
  | Host port       | `5432` (published on `0.0.0.0`)                                       |
  | Docker network  | `database_default` (external network for our compose file)            |
  | Volume          | `database_postgres_data` → `/var/lib/postgresql`                      |
  | Owned by        | compose project `database` in `../OrderManagementSystem/Database`     |
  | Other databases | `order_management` — belongs to another project, **never touch it**   |

- The container is **shared with the OrderManagementSystem project**. This app only ever uses its
  own databases and role; never run migrations, drops or grants against `order_management`,
  and never use the `postgres` superuser from application code.
- One-time setup (run by the user as `postgres`): role `drogueria_app` (LOGIN, no superuser),
  databases `drogueria_starling` and `drogueria_starling_test` owned by `drogueria_app`,
  extension `pg_trgm` in both.
- Connect through `DATABASE_URL` from `.env` (never hard-code credentials; `.env` is git-ignored,
  `.env.example` documents the variables).
- Local dev (API on the host): `postgresql+asyncpg://<user>:<pass>@localhost:<port>/<db>`.
- API in Docker: attach the `api` service to the external network `database_default` and use
  `order-management-db:5432` as host.
- Use a dedicated database (`drogueria_starling`) and a dedicated app role, not the `postgres`
  superuser. Tests use a separate database (`drogueria_starling_test`).
- Schema changes only through Alembic migrations — never `create_all()` outside tests.

## Implementation prompt

> Build the Drogueria Starling MVP in this repository following the architecture in
> `docs/architecture.png` and every rule in this file.
>
> 1. **Backend skeleton** — FastAPI app under `backend/` with the layout above, settings loaded
>    from `.env`, async SQLAlchemy session, Alembic configured against `DATABASE_URL`,
>    `/api/v1/health` endpoint that checks DB connectivity, OpenAPI docs enabled.
> 2. **Auth & users** — OAuth2 password flow with JWT (short-lived access token + refresh),
>    bcrypt/argon2 password hashing, roles `admin`, `pharmacist`, `cashier`; enforce permissions
>    per endpoint with a dependency. Seed one admin via a CLI command, not a migration.
> 3. **Catalog** — products, categories, active ingredients, presentations, barcodes,
>    sanitary registration number, prescription flag, controlled flag, tax rate, price.
>    Search by name, active ingredient and barcode (pg_trgm index for name).
> 4. **Inventory** — lots with lot number and expiry date, stock per lot, immutable
>    `stock_movements` ledger (purchase, sale, return, adjustment, expiry write-off).
>    Stock on hand is derived from lots; FEFO picking for sales.
> 5. **Purchasing** — suppliers, purchase orders, goods receipt that creates lots and movements.
> 6. **POS / Sales** — cart, pricing, discounts, taxes, multiple payment methods, receipt
>    numbering, returns/voids. Checkout is one DB transaction (sale + lot decrements + movements +
>    payments) with row locks on the affected lots.
> 7. **Customers & prescriptions** — customer records and prescription capture linked to sale
>    lines for Rx/controlled products.
> 8. **Reports & audit** — daily sales, cash closing per register shift, stock valuation,
>    expiring-soon list, low stock; audit log for every create/update/delete on business data.
> 9. **Jobs** — daily expiry and low-stock alerts (APScheduler).
> 10. **Frontend** — Vue 3 SPA with login, POS screen (barcode-first, keyboard-driven,
>     works with a USB scanner as keyboard input), catalog, inventory, purchasing, customers,
>     reports; role-based navigation; Spanish UI by default with i18n.
> 11. **Delivery** — `docker-compose.yml` for `api` and `web` (Nginx) connecting to the existing
>     Postgres container; README with setup steps.
>
> Work in small, reviewable increments, one module at a time, each with migrations, tests
> (pytest for services and endpoints, Vitest for stores/components) and passing lint
> (ruff + mypy, eslint + vue-tsc). Every rule in `docs/business-rules.csv` must be covered by
> at least one automated test. If a rule is ambiguous or conflicts with a request, stop and ask.

## Strict business rules

These are non-negotiable. Enforce them in the **service layer** (and with DB constraints where
possible), never only in the UI.

The full rule text lives in [docs/business-rules.csv](docs/business-rules.csv)
(columns: `Rule Code`, `Description`, `Rule category`). Read it before changing business logic,
and refer to rules by code (e.g. `INV-1`) in code comments, tests and commits.

| Rule category        | Code prefix |
|----------------------|-------------|
| Inventory & expiry   | `INV`       |
| Catalog & regulatory | `CAT`       |
| Sales & money        | `SAL`       |
| Security & audit     | `SEC`       |

Codes are numbered within each category and never reused; a new rule takes the next free
number in its category.

## Assumptions (confirm or correct)

- **Country**: Guatemala. GTQ currency, date format dd-mmm-yyyy
  IVA taxes, Spanish UI, and electronic invoicing as a future integration.
- **Single store, multiple registers** for the MVP; schema keeps a `store_id` so multi-store
  can be added later.
- **Currency**: GTQ with 2 decimals stored (display may hide them).
- **Taxes**: per-product tax rate (12%); prices entered tax-included.
- **Roles**: `admin`, `pharmacist`, `cashier` are enough for the MVP.
- **E-invoicing (SAT)** and card payment terminals are out of MVP scope; sales produce an
  internal receipt. The design keeps a hook for an invoicing provider.
- **Online-only POS** for the MVP (no offline mode).
- **Purchasing** is included (needed to bring lots and expiry dates into stock).
- **Background jobs** use APScheduler inside the API process; move to Celery/RQ if needed.
- **Peripherals**: barcode scanner as keyboard input; receipts printed through the browser
  print dialog (80 mm layout). No direct ESC/POS driver in the MVP.
- The cashier discount limit, store timezone and expiry "warning window" (default 90 days)
  are configurable settings.

## Conventions

- Python: ruff (lint + format), mypy strict on `app/`. TypeScript: eslint + prettier, `vue-tsc`.
- Business logic only in `services/`; routers and Vue components stay thin.
- API errors return `{ "detail": ..., "code": ... }` with stable error codes the UI can translate.
- Git: work on `dev`, PRs to `main`, small commits, always confirm before commit.
