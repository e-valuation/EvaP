from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0131_userprofile_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="textanswer",
            name="is_flagged",
            field=models.BooleanField(default=False, verbose_name="is flagged"),
        ),
    ]
