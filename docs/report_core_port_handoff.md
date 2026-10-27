# Shared Report-Core Port Handoff

Source reviewed read-only: `D:\WebProjects\property_mgmt_security_review`.

Authoritative source map:

- `docs/report_audit_coverage.md`
- `main/test_report_audit.py`
- migrations `0085_financialentry_property.py` and `0086_rentrollsnapshot_tenancy_unique.py`
- verified PostgreSQL locking pattern already ported separately

## Why the remaining port must be a fresh task

RentalReadyPro is not schema-equivalent to BowlingLegacy in three areas required by the requested port:

1. `FinancialEntry` has no stable `property` foreign key. This can be added safely as RentalReadyPro migration `0055` with the verified unique-name-only backfill.
2. RentalReadyPro has no `RentRollSnapshot` model, so BowlingLegacy migration `0086` and its tenancy uniqueness constraint have no direct target.
3. RentalReadyPro has no `ResidentBalanceEntry` ledger and uses `resident_file_status` (`active`, `archived`, `unit_file`) rather than BowlingLegacy's `application_folder` plus `tenancy_status`. Deposit application and move-out allocation cannot be copied without first deciding whether to port the balance-ledger model and how existing RentalReadyPro balances map into it.

Implementing items 2 and 3 is a domain-model expansion with data migration and compatibility consequences. It should not be mixed into the already-tested security/membership work without a fresh context and explicit migration review.

## Safe phased implementation map

### Phase A: stable financial attribution

1. Add nullable `FinancialEntry.property = ForeignKey(Property, SET_NULL, related_name="financial_entries")`.
2. Add migration `0055_financialentry_property`.
3. Backfill only rows with `ledger_scope="property"`:
   - Set the FK when `property_name` matches exactly one `Property`.
   - If `property_name` is blank, use `upload.property_id` only when present.
   - Leave duplicate-name, company, and ambiguous rows unresolved.
4. Port `financial_entries_for_properties()` and replace name/upload scoping in custom reports, T-12, income statement, and related helpers.
5. Populate the FK in import parsing and accounting-receipt/split entry creation.
6. Add known-answer coverage for mixed bank uploads, company rows, duplicate names, and legacy unique-name rows.

### Phase B: period and allocation parity

1. Port `payment_month_allocations()` with cent remainder assigned to the final covered month.
2. Use allocations consistently in income statement, T-12, move-out calculations, and exports.
3. Preserve per-property/per-month spreadsheet precedence before portfolio aggregation.
4. Limit annual projection basis to elapsed months.
5. Port reversed/invalid date validation and generated-report suppression.
6. Add print metadata for property scope, period/basis, and generation date.

### Phase C: rent-roll tenancy model decision

Before coding, choose one reviewed approach:

- Introduce a RentalReadyPro snapshot/history model equivalent to BowlingLegacy and migrate existing rows; or
- Implement current/effective tenancy selection without snapshot persistence and explicitly defer historical uniqueness.

Do not manufacture `application_folder` or `tenancy_status` fields. Adapt occupancy rules to `resident_file_status`, `lease_start_date`, and `move_out_date`. Required known answers include future tenants not replacing current occupants, overlapping tenancies remaining distinct, actual charge separated from scheduled rent and prior balance, and property/resident fields in CSV.

### Phase D: deposit and move-out ledger decision

BowlingLegacy's verified behavior depends on `ResidentBalanceEntry`, which RentalReadyPro lacks. Decide whether to port that model and migration before porting:

- Deposit held after prior deposit application.
- Former-resident deposit receivables.
- Move-out charge/payment service-month allocation.
- Deposit credit capped to the remaining statement balance.

Preserve the documented unresolved policy: waiver and refund need first-class ledger event types and must not be inferred.

### Phase E: surfaces and KPIs

Selectively port after Phases A-D:

- Payment log population and `month=all` behavior.
- Safe CSV text neutralization for values beginning with `=`, `+`, `-`, or `@`.
- Rent roll and T-12 HTML/CSV parity.
- Payment reference fallback: manual reference, Stripe intent, then Stripe session.
- Property financial KPIs based on scoped current rent receipts and shared T-12 rows.
- Owner YTD metrics limited to elapsed months and excluding service credits.

Do not port property-specific narrative, named-person overrides, acquisition values, grant figures, or BowlingLegacy branding.

## Test plan

Adapt all eight known-answer tests from BowlingLegacy `main/test_report_audit.py` to RentalReadyPro's approved schema. Add duplicate-name migration tests and CSV formula-neutralization assertions.

Run, in order:

1. Migration tests and `makemigrations --check --dry-run`.
2. Focused report audit tests.
3. Focused membership/private-media/Stripe tests.
4. Full PostgreSQL 17 suite at `127.0.0.1:55432` using a unique synthetic database.
5. Full SQLite suite, expecting only row-lock contract skips.
6. `manage.py check` and `git diff --check`.

Use `connections.close_all()` in every PostgreSQL worker thread's `finally` block. Do not push until the integrated port has completed this matrix and received review.
