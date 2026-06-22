# Accounting Import Sample Pack

These files are synthetic test fixtures for RentalReadyPro import development. They are not copied from a real owner, tenant, bank, or accounting account.

Use them to test whether the financial upload flow can recognize common export shapes from accounting tools, banks, and property management systems.

## Files

- `quickbooks_profit_and_loss_summary.csv`
  - Tests a profit and loss summary with accounts down the left side and months across the top.
  - Important rows: rental income, other income, operating expenses, debt service, NOI-style totals.

- `quickbooks_general_ledger_detail.csv`
  - Tests a detail ledger export with date, transaction type, account, vendor/customer, memo, debit, credit, and balance.
  - Useful for classifying operating expenses, owner draws, debt payments, and income.

- `xero_account_transactions.csv`
  - Tests a Xero-style account transaction export with source, contact, reference, debit, credit, tax, and account fields.

- `bank_activity_export.csv`
  - Tests a plain bank CSV with posted date, description, withdrawals, deposits, and balance.
  - Important because many owners will only have bank activity, not clean books.

- `appfolio_owner_statement.csv`
  - Tests a property-management owner statement layout with property, unit, tenant, income, expenses, management fees, and owner distribution.

- `buildium_rent_roll.csv`
  - Tests rent-roll import with unit, resident, lease dates, recurring charges, deposits held, and balance.

- `yardi_gl_detail.csv`
  - Tests a general-ledger detail export with property code, book, account number, period, batch, debit, and credit.

- `rent_manager_charge_payment_ledger.csv`
  - Tests resident ledger rows where charges and payments are mixed together by unit and resident.

- `receipt_expense_log.csv`
  - Tests receipt-backed expense entry with vendor, category, payment method, receipt file name, and approval status.

## Import Goals

The import system should eventually be able to:

1. Detect whether a file is a summary, transaction detail, rent roll, bank activity, resident ledger, or receipt log.
2. Let the owner map columns when automatic detection is uncertain.
3. Prevent duplicate counting when a summary and detailed records cover the same month.
4. Preserve source file, source row, and mapping decisions for audit trail.
5. Classify income, operating expense, debt service, deposit liability, owner draw, capital improvement, and excluded/non-property company expense.
6. Keep all imported records property-scoped so owner and landlord data never crosses properties.

## Suggested Test Order

1. Start with `quickbooks_profit_and_loss_summary.csv`.
2. Add `bank_activity_export.csv`.
3. Add `buildium_rent_roll.csv`.
4. Add `appfolio_owner_statement.csv`.
5. Add the detail-ledger files last and confirm they do not double count against summary rows.
