from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0019_merge"),
    ]

    operations = [
        migrations.AlterField(
            model_name="course",
            name="vote_end_date",
            field=models.DateField(null=True, verbose_name="last day of evaluation"),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="course",
            name="vote_start_date",
            field=models.DateField(null=True, verbose_name="first day of evaluation"),
            preserve_default=True,
        ),
    ]
