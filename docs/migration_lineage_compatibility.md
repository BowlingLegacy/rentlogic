# BowlingLegacy / RentalReadyPro migration compatibility

## Candidate basis

- BowlingLegacy release commit: `35c7867ed14dac21748a7fec6ef4873f7bc00c37`.
- BowlingLegacy release leaf: `main.0086_rentrollsnapshot_tenancy_unique`.
- Demo-Mode production shape before this candidate: BowlingLegacy history through
  `main.0084_correct_jeffery_bowling_year` and no RentalReadyPro branch.
- Candidate merge leaf: `main.0087_merge_bowlinglegacy_rentalready`.
- `PROPERTY_MEMBERSHIP_ENFORCEMENT` remains disabled by default.

Migration identity is the complete `(app_label, migration_name)` pair. The
candidate therefore retains both named branches and merges them; it does not
fake migrations based on their numeric prefixes.

## Compatibility behavior

The BowlingLegacy schema migrations are represented under their exact applied
names. Its customer-specific correction migrations (`0047` through `0084`,
except the schema-bearing `0052` and `0069`) are intentional no-op markers in
RentalReadyPro. This recognizes an already-applied BowlingLegacy database but
does not manufacture named residents, payments, receipts, expenses, properties,
or historical rent-roll rows on a new RentalReadyPro database.

Shared BowlingLegacy structures preserved in the model state are:

- `AccountingPeriod` and `VendorCategoryRule`;
- application folder and tenancy archive fields alongside RentalReadyPro's
  `resident_file_status`;
- `ResidentBalanceEntry`, without a historical backfill;
- `RentRollSnapshot`, without generated historical snapshots;
- SMS delivery fields and multi-intake resident-file linkage;
- `AccountingReceiptSplit`, with its creator and protected category; and
- stable `FinancialEntry.property` attribution with the conservative `0085`
  backfill.

RentalReadyPro migrations that formerly duplicated `move_out_date`,
`AccountingReceiptSplit`, and `FinancialEntry.property` now retain their exact
history identities without issuing duplicate DDL. The BowlingLegacy migrations
own those shared objects.

The intake relationship remains BowlingLegacy's one-to-many relationship.
RentalReadyPro rent-setup reads use a prefetched collection and do not collapse
or delete duplicate historical intake records.

No mapping is inferred between `resident_file_status`, `application_folder`,
and `tenancy_status`. New rows receive each field's existing default; later
workflow changes must update the fields deliberately. No payment, refund,
waiver, deposit-ledger entry, move-out entry, or rent-roll snapshot is inferred.
Unpaid deposits continue to be represented by `deposit_required - deposit_paid`
and remain collectible until an explicit payment or future first-class waiver
event changes that state.

## Validation evidence

All databases below were disposable local PostgreSQL 17.11 databases containing
no production data.

| Path | Result |
| --- | --- |
| Fresh database through both branches and `0087` | Passed |
| BowlingLegacy `0084` baseline to candidate leaf | Passed |
| BowlingLegacy release `0086` baseline to candidate leaf | Passed |
| Full PostgreSQL test suite | 271/271 passed |
| Full SQLite test suite | 271 passed; 2 expected row-lock skips |
| `makemigrations --check --dry-run` | No changes detected |
| Django system check | No issues |

## Production topology and gate

`rentlogic-1` uses the separate `Demo-Mode-postgres` database. BowlingLegacy
uses `bowlinglegacy-postgres`; the databases are not shared. The legacy
`rentlogic-cly7` service has no PostgreSQL environment attachment.

Render's read-only database metadata confirms Demo-Mode is available,
PostgreSQL 18, on the paid `basic_256mb` plan, with HA disabled and no read
replicas. The API does not expose its actual recovery points or logical exports.
Before deployment, an operator must verify in the Demo-Mode database dashboard
that a current PITR recovery point or completed logical export exists.

## Rollback

Do not reverse the merged migration graph in place after traffic resumes:
reversing the RentalReadyPro branch would drop its additive tables and fields.
For a failed pre-traffic deployment, stop the release and restore the prior
application commit. If any migration reached Demo-Mode, restore the verified
pre-deploy database recovery point/export before returning the old application
to service. Do not use `--fake`, delete migration records, or manually drop
shared BowlingLegacy columns.

Deployment should pin an exact reviewed commit to `rentlogic-1`. Do not push or
promote `main`, because the legacy `rentlogic-cly7` service also auto-deploys
from that branch.
