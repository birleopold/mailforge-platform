from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("domains", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="dns_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domain",
            name="dns_checks",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
