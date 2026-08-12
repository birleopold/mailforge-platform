from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mailboxes", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="alias",
            name="backend_identifier",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="alias",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
