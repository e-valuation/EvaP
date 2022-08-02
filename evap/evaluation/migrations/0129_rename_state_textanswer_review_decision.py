from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0128_django_40_noop"),
    ]

    operations = [
        migrations.RenameField(
            model_name="textanswer",
            old_name="state",
            new_name="review_decision",
        ),
    ]
