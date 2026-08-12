from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("domains", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Mailbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("local_part", models.CharField(max_length=64)),
                ("display_name", models.CharField(blank=True, max_length=200)),
                ("quota_mb", models.PositiveIntegerField(default=5120)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("provisioning", "Provisioning"), ("active", "Active"), ("suspended", "Suspended"), ("deleted", "Deleted")], default="pending", max_length=20)),
                ("backend_identifier", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("domain", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mailboxes", to="domains.domain")),
            ],
        ),
        migrations.CreateModel(
            name="Alias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("local_part", models.CharField(max_length=64)),
                ("destinations", models.JSONField(default=list)),
                ("active", models.BooleanField(default=True)),
                ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="aliases", to="domains.domain")),
            ],
        ),
        migrations.AddConstraint(
            model_name="mailbox",
            constraint=models.UniqueConstraint(fields=("domain", "local_part"), name="uniq_mailbox_localpart_per_domain"),
        ),
        migrations.AddConstraint(
            model_name="alias",
            constraint=models.UniqueConstraint(fields=("domain", "local_part"), name="uniq_alias_localpart_per_domain"),
        ),
    ]
