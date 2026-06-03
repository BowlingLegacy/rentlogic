from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0002_manual_sync_existing_db'),
    ]

    operations = [
        migrations.CreateModel(
            name='SignedDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(default='other', max_length=50)),
                ('title', models.CharField(max_length=255)),
                ('property_name', models.CharField(blank=True, max_length=255)),
                ('property_address', models.CharField(blank=True, max_length=255)),
                ('resident_name', models.CharField(blank=True, max_length=255)),
                ('room_space', models.CharField(blank=True, max_length=100)),
                ('monthly_rent', models.DecimalField(decimal_places=2, default=0.00, max_digits=10)),
                ('utility_fee', models.DecimalField(decimal_places=2, default=0.00, max_digits=10)),
                ('security_deposit', models.DecimalField(decimal_places=2, default=0.00, max_digits=10)),
                ('lease_start_date', models.DateField(blank=True, null=True)),
                ('landlord_name', models.CharField(default='Michael Bowling', max_length=255)),
                ('landlord_signature', models.CharField(default='Michael Bowling', max_length=255)),
                ('lease_sent_date', models.DateField(blank=True, null=True)),
                ('rent_initials', models.CharField(blank=True, max_length=10)),
                ('sobriety_initials', models.CharField(blank=True, max_length=10)),
                ('testing_initials', models.CharField(blank=True, max_length=10)),
                ('guest_policy_initials', models.CharField(blank=True, max_length=10)),
                ('cleanliness_initials', models.CharField(blank=True, max_length=10)),
                ('disclosure_initials', models.CharField(blank=True, max_length=10)),
                ('resident_signature', models.CharField(blank=True, max_length=255)),
                ('signature_agreement', models.BooleanField(default=False)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('locked', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='signed_documents', to='main.housingapplication')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
