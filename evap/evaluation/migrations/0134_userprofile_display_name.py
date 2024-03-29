# Generated by Django 4.1.7 on 2023-03-10 22:36

from django.db import migrations, models
import django.db.models.functions


class Migration(migrations.Migration):
    dependencies = [
        ("evaluation", "0133_add_infotext_model"),
    ]

    operations = [
        migrations.RenameField(
            model_name="userprofile",
            old_name="first_name",
            new_name="first_name_given",
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="first_name_given",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="given first name"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="first_name_chosen",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="display name"),
        ),
        migrations.AlterModelOptions(
            name="userprofile",
            options={
                "ordering": [
                    django.db.models.functions.text.Lower("last_name"),
                    django.db.models.functions.text.Lower(
                        django.db.models.functions.comparison.Coalesce(
                            django.db.models.functions.comparison.NullIf("first_name_chosen", models.Value("")), "first_name_given"
                        )
                    ),
                    django.db.models.functions.text.Lower("email"),
                ],
                "verbose_name": "user",
                "verbose_name_plural": "users",
            },
        ),
    ]
