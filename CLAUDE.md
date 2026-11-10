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
> (ruff + mypy, eslint + vue-tsc). Every rule under **Strict business rules** must be covered by
> at least one automated test. If a rule is ambiguous or conflicts with a request, stop and ask.

## Strict business rules

These are non-negotiable. Enforce them in the **service layer** (and with DB constraints where
possible), never only in the UI.

### Inventory & expiry
1. Stock can never go negative — at product or lot level. A sale that exceeds available stock
   is rejected, not partially fulfilled.
2. Every product unit belongs to a lot with a lot number and an expiry date. No lot, no stock.
3. Expired lots cannot be sold. A lot is sellable only if `expiry_date > today` (store timezone).
4. Sales consume stock **FEFO** (first expired, first out) unless a pharmacist overrides it,
   and the override is audited.
5. Stock changes only through `stock_movements` entries. Movements are append-only: never
   updated or deleted; corrections are new compensating movements.
6. Manual adjustments and expiry write-offs require `pharmacist` or `admin` and a reason.

### Catalog & regulatory
7. sanitary registration number is an optional field.
8. Products flagged `requires_prescription` can only be sold with a prescription reference
   attached to the sale line, should accept jpg, jpeg, png or pdf
9. Products flagged `controlled` additionally require: customer identification, prescriber data,
   a pharmacist's approval on the sale, and quantity no greater than what the prescription allows.
10. Products are deactivated, never hard-deleted, once they have movements or sales.

### Sales & money
11. All money uses `NUMERIC(14,2)` in the DB and `Decimal` in Python — never floats.
    Rounding is half-up at line level, then totals are summed.
12. Checkout is atomic: sale, lines, lot decrements, stock movements and payments are written in
    one transaction, or nothing is written.
13. Sum of payments must equal the sale total (change is computed for cash, not stored as payment).
14. Prices and tax rates are copied onto each sale line at the moment of sale; later catalog
    changes never alter past sales.
15. Completed sales are immutable. Corrections are done with a return or void document that
    references the original sale and restocks via movements.
16. Voids are allowed only for the same register shift and require `pharmacist`/`admin`.
    Returns of Rx/controlled products require pharmacist approval.
17. Discounts above the configured cashier limit require `pharmacist`/`admin` authorization.
    A sale price can never be below cost unless an admin authorizes it.
18. Receipt/invoice numbers are sequential, gap-free per register, and never reused.
19. A cashier must open a register shift (opening cash) before selling and close it (counted
    cash vs. expected) at the end; the difference is recorded, not hidden.

### Security & audit
20. Every create/update/delete on business data writes an audit log entry
    (who, when, what, before/after). Audit entries are append-only.
21. Role permissions are checked on the backend for every endpoint.
22. Customer and prescription data are personal/health data: only the roles that need them can
    read them, and they never appear in logs.
23. All timestamps are stored in UTC (`timestamptz`); business dates (expiry, shift date) use the
    store's configured timezone.

## Assumptions (confirm or correct)

- **Country**: Guatemala (the name "droguería"). GTQ currency,
  IVA taxes, Spanish UI, and electronic invoicing as a future integration.
- **Single store, multiple registers** for the MVP; schema keeps a `store_id` so multi-store
  can be added later.
- **Currency**: GTQ with 2 decimals stored (display may hide them).
- **Taxes**: per-product tax rate (12%); prices entered tax-included.
- **Roles**: `admin`, `pharmacist`, `cashier` are enough for the MVP.
- **E-invoicing (DIAN)** and card payment terminals are out of MVP scope; sales produce an
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
