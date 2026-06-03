from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Repairs missing rent/payment/space database fields after migration reset"

    def handle(self, *args, **kwargs):
        sql = """
        ALTER TABLE main_housingapplication
        ADD COLUMN IF NOT EXISTS monthly_rent numeric(10,2) NOT NULL DEFAULT 0.00;

        ALTER TABLE main_housingapplication
        ADD COLUMN IF NOT EXISTS balance numeric(10,2) NOT NULL DEFAULT 0.00;

        ALTER TABLE main_housingapplication
        ADD COLUMN IF NOT EXISTS rent_due_day integer NOT NULL DEFAULT 1;

        ALTER TABLE main_housingapplication
        ADD COLUMN IF NOT EXISTS space_type varchar(50) NOT NULL DEFAULT '';

        ALTER TABLE main_housingapplication
        ADD COLUMN IF NOT EXISTS space_label varchar(50) NOT NULL DEFAULT '';

        CREATE TABLE IF NOT EXISTS main_payment (
            id BIGSERIAL PRIMARY KEY,
            amount numeric(10,2) NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'pending',
            stripe_session_id varchar(255) NOT NULL DEFAULT '',
            stripe_payment_intent varchar(255) NOT NULL DEFAULT '',
            created_at timestamp with time zone NOT NULL DEFAULT NOW(),
            application_id bigint NOT NULL REFERENCES main_housingapplication(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS main_payment_application_id_idx
        ON main_payment(application_id);

        CREATE TABLE IF NOT EXISTS main_renthistory (
            id BIGSERIAL PRIMARY KEY,
            rent_amount numeric(10,2) NOT NULL,
            effective_date date NOT NULL,
            created_at timestamp with time zone NOT NULL DEFAULT NOW(),
            application_id bigint NOT NULL REFERENCES main_housingapplication(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS main_renthistory_application_id_idx
        ON main_renthistory(application_id);
        """

        with connection.cursor() as cursor:
            cursor.execute(sql)

        self.stdout.write(self.style.SUCCESS("Rent/payment/space schema repaired successfully."))
