from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domains", "0002_domain_dns_checked_at_domain_dns_checks"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="dns_zone_file",
            field=models.TextField(blank=True),
        ),
    ]
