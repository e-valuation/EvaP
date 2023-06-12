# Generated by Django 4.1.5 on 2023-05-22 18:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0133_add_infotext_model'),
    ]

    operations = [
        migrations.CreateModel(
            name="VoteTimestamp",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True, verbose_name="vote timestamp")),
                (
                    "evaluation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="evaluation.evaluation"),
                ),
            ],
        ),
    ]
