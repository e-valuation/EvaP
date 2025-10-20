import django_fsm
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0006_archiving_and_order_default"),
    ]

    operations = [
        migrations.AlterField(
            model_name="course",
            name="state",
            field=django_fsm.FSMField(max_length=50, default="new"),
            preserve_default=True,
        ),
    ]
