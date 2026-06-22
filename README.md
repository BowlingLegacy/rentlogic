# RentalReadyPro

RentalReadyPro is a property operations and reporting platform for owners, landlords, and residents. It supports resident files, rent and payment ledgers, receipt-backed accounting records, owner reports, listings, applicant screening workflows, SMS/email notifications, and property-branded resident dashboards.

## Primary Services

- Production web service: `rentlogic-1`
- Public domain: `rentalreadypro.com`
- Alternate/redirect domain: `rentalledgerpro.com`
- Render fallback URL: `https://rentlogic-1.onrender.com`
- Demo URL: configured through `DEMO_PUBLIC_URL` when available

## Key Environment Variables

- `SECRET_KEY`
- `DEBUG` or `DJANGO_DEBUG`
- `ALLOWED_HOSTS`
- `DATABASE_URL`
- `DEFAULT_FROM_EMAIL`
- `RENTAL_LEDGER_LEAD_EMAIL`
- `STRIPE_PUBLIC_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `TELNYX_API_KEY`
- `TELNYX_FROM_NUMBER`
- `DEMO_MODE`
- `DEMO_PUBLIC_URL`
- `DEMO_ADMIN_USERNAME`
- `DEMO_SESSION_SECONDS`
- `APP_STORE_URL`
- `GOOGLE_PLAY_URL`

## Render Commands

Build command:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput
```

Pre-deploy command:

```bash
python manage.py migrate
```

Start command:

```bash
gunicorn core.wsgi:application
```

## Launch Checklist

1. Confirm `rentalreadypro.com` and `www.rentalreadypro.com` are verified in Render.
2. Confirm `rentalledgerpro.com` and `www.rentalledgerpro.com` redirect or remain attached as alternate domains during the transition.
3. Confirm `ALLOWED_HOSTS` includes both RentalReadyPro and RentalLedgerPro domains plus the Render service host.
4. Confirm the production database is connected with `DATABASE_URL`.
5. Run migrations successfully.
6. Create or confirm the first superadmin user.
7. Confirm owner intake sends lead notification emails.
8. Confirm the demo service URL is configured if available.
9. Confirm Stripe keys are production or test keys as intended.
10. Confirm SMS provider configuration before sending real texts.
11. Confirm privacy policy, terms, and contact page are live.

## First Customer Setup Checklist

1. Owner intake submitted.
2. Owner account created and invited.
3. First property created.
4. Property units or rooms imported or entered.
5. Current resident list imported.
6. Resident setup codes generated and sent.
7. Tenant files, leases, and scans uploaded where available.
8. Payment categories, receipt categories, and vendors reviewed.
9. Stripe and SMS settings confirmed for that property.
10. Rent roll, payment ledger, T-12, NOI, and custom reports verified.

## Demo Reset

Demo mode is controlled by `DEMO_MODE`. If using a separate demo database, keep demo data isolated from production and reset it with the configured Render cron job or management command used by the deployment.
