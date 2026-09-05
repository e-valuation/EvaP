from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rewards", "0007_localize_rewardpointredemption_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="rewardpointgranting",
            name="contributes_to_status",
            field=models.BooleanField(default=True, verbose_name="contributes to status"),
        ),
    ]
