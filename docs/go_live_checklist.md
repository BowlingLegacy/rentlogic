# RentalReadyPro Go-Live Checklist

Use this checklist for each new owner or property so setup is repeatable and sales handoff does not depend on memory.

## 1. Owner Account

- Owner setup questionnaire submitted from `/property-owner-intake/`.
- Junk/spam submissions reviewed with `python manage.py cleanup_spam_owner_intakes`.
- Owner portal access code sent and account login confirmed.
- Owner dashboard opens without demo data.
- Billing plan, trial status, and owner contact details reviewed.

## 2. Property Folder

- Property record created with name, address, owner email, landlord email, unit count, and public listing settings.
- Property photos uploaded where available.
- Utility setup notes entered if tenants must open their own accounts.
- Renters insurance referral URL entered if the property uses one.
- Application fee, background check, and screening settings reviewed.

## 3. Resident Setup

- Current resident roster uploaded from the owner dashboard.
- Units, names, phone numbers, email addresses, rent, utilities, deposits, last month rent, and open balances previewed before import.
- Duplicate resident records checked before sending setup codes.
- Setup codes sent only to active residents who still need login access.
- Completed resident setup attempts are hidden from the needs-attention list.

## 4. Tenant Files

- Existing leases, IDs, applications, notices, and deposit records uploaded through tenant file packet upload.
- Scanned files reviewed and attached to the correct resident file.
- Signed onboarding documents confirmed for each active resident.
- Former residents are archived separately from applicants.

## 5. Payments

- Stripe platform keys configured.
- Owner-level or property-level Stripe Connect routing selected.
- Test payment run in the correct environment only.
- Combined payments split into rent, deposit, and utility ledger lines automatically.
- Upcoming rent payment button verified for residents who want to pay next month early.
- Demo payments confirmed disabled on production-looking hosts.

## 6. SMS And Email

- Email diagnostic passes before inviting owners or residents.
- SMS provider keys and from-number configured.
- 10DLC campaign active if sending production SMS.
- Resident SMS consent recorded from lease, written form, verbal consent, or resident setup.
- Staff-copy SMS delivery tested after deploy.

## 7. Accounting

- Receipt upload tested with a normal invoice.
- Split receipt tested for one invoice with multiple categories.
- Bank/CSV import previewed before posting.
- Duplicate receipts marked ignored instead of counted twice.
- Utilities categorized consistently under power, gas, water, sewer, trash, internet, cable, phone, and fees.

## 8. Reports

- Rent roll checked by property and month.
- Payment log checked by property and month.
- T-12 checked against known source totals.
- Custom report saved and re-run from the reports page.
- Vendor expense, utility trend, capital log, valuation estimate, deposit liability, and insurance compliance reviewed where data exists.

## 9. Listings And Applicants

- Vacancy listing created from the property folder.
- Listing has unit photos, exterior photos, rent, deposit, utilities, benefits, and application link.
- Application form requires identity, income history, employment/fixed income duration, vehicle info, and required uploads.
- Applicant screening score reviewed as an aid only; owner makes final decision.
- Adverse action notice workflow available when needed.

## 10. Sales Handoff

- Public site uses `rentalreadypro.com`.
- Home page has clear `Start Owner Setup`, `Preview Demo`, `Login`, and `Open App` paths.
- Demo data is separate from production.
- Contact page shows direct phone and email.
- Pricing menu, savings story, and referral revenue lanes are ready to discuss.
