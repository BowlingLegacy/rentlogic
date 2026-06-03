# Demo Mode

Demo mode is designed for a separate Render service and a separate demo database.
Do not enable it on the live Bowling Legacy service.

## Render Environment

Set these variables on the demo service only:

```text
DEMO_MODE=True
DEMO_ALLOWED_HOSTS=your-demo-domain.onrender.com
DEMO_SESSION_SECONDS=7200
DEMO_ADMIN_USERNAME=demo-admin
```

Use a separate PostgreSQL database for the demo service. Do not point demo mode at the live Bowling Legacy database.

## Reset Command

Run this after deploy and from a scheduled Render cron job every 2 hours:

```bash
python manage.py reset_demo_environment --confirm
```

The command refuses to run unless `DEMO_MODE=True`.

## Public Demo Entry

Visitors can open:

```text
/demo/
```

That signs them into the seeded demo admin workspace. Demo payments are recorded as fake completed demo payments and do not open Stripe.
