from django.db import migrations, models
import django.db.models.deletion
import apps.domains.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenants", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Domain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=253, unique=True)),
                ("status", models.CharField(choices=[("pending_verification", "Pending verification"), ("verified", "Verified"), ("provisioning", "Provisioning"), ("dns_configuration", "DNS configuration"), ("active", "Active"), ("suspended", "Suspended"), ("decommissioned", "Decommissioned")], default="pending_verification", max_length=32)),
                ("ownership_token", models.CharField(default=apps.domains.models.verification_token, editable=False, max_length=128)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("backend", models.CharField(default="stalwart", max_length=32)),
                ("backend_identifier", models.CharField(blank=True, max_length=255)),
                ("sending_enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="domains", to="tenants.tenant")),
            ],
        ),
    ]
