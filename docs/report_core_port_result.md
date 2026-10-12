# Shared Report-Core Port Result

Source reviewed read-only: `D:\WebProjects\property_mgmt_security_review`.

## Coverage / parity matrix

| Contract | RentalReadyPro result | Evidence / limit |
|---|---|---|
| Stable financial row attribution | Implemented | Nullable `FinancialEntry.property`; conservative `0055` backfill; company rows remain null; unique-name-only legacy fallback. |
| Property/month source precedence | Implemented | T-12 resolves spreadsheet/portal/receipt precedence independently for each property before portfolio aggregation. |
| Service-month cent allocation | Implemented | Final month receives the cent remainder; shared by T-12 and existing report payment math. |
| T-12 cash-flow and projection basis | Implemented | Capital is included in net cash flow; current-year annualization uses elapsed months only. |
| Reversed report dates | Implemented | Form-level validation suppresses generated output and displays the error. |
| Payment and rent-roll CSV safety/parity | Implemented in safe existing-model scope | Formula-like text is apostrophe-neutralized; payment CSV includes property/unit/method/reference; rent-roll CSV includes property. |
| Payment reference precedence | Implemented | Manual reference, then Stripe intent, then Stripe session. |
| Current/future rent-roll selection | Existing current-model behavior retained | No historical snapshots added or fabricated. Full BowlingLegacy snapshot parity remains deferred. |
| Deposit liability and move-out ledger allocation | Not ported | RentalReadyPro has no `ResidentBalanceEntry`; current aggregate balances cannot safely identify payment, application, waiver, or refund events. |
| Historical occupancy/rate snapshots | Not ported | RentalReadyPro has no `RentRollSnapshot` or effective-dated room/lease history. |

## Migration 0055 behavior and risk

- Adds a nullable `FinancialEntry.property` foreign key with `SET_NULL`; schema rollback removes only the new field.
- Backfills only `ledger_scope="property"` rows.
- Exact property name is accepted only when it identifies one property globally.
- A blank name can use the upload property only for a property-ledger row.
- Duplicate-name, bank/company, and otherwise ambiguous rows remain null.
- Reverse data migration is a no-op; rollback removes the column without changing legacy text attribution.

## Verification

- Focused shared-core tests: 7 passed on SQLite.
- Full SQLite suite: 269 tests ran successfully, including 2 expected row-lock skips.
- Full PostgreSQL 17.11 suite: 269 tests passed with no skips against the isolated local test database.
- `manage.py check`: passed.
- `makemigrations --check --dry-run`: no changes detected.
- PostgreSQL 17.11 was exercised at `127.0.0.1:55432` using isolated base database `rentlogic_report_port_20261012`. Python 3.12.10 and the existing project virtual environment were healthy; initial access failures were caused by filesystem sandbox denial. `POSTGRES_SSLMODE=disable` was used only for the local non-SSL test server. Application settings still default to `require` when that explicit override is absent. No production database was accessed.

## Decisions still required

1. Approve an additive `ResidentBalanceEntry` event ledger (charge/payment/deposit application/waiver/refund) and define forward-only writes. Existing balances must remain opening balances; no historic event inference.
2. Approve a `RentRollSnapshot` / effective-dated tenancy model, including how room transfers and overlapping occupants are represented. Existing current rows may seed only a present-state baseline, not historical months.
3. Confirm whether deposit refunds and waivers both reduce collectible deposit and held liability, and which user roles may record/reverse each event.
