from django.db import migrations
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0121_add_allows_textanswers_to_question'),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluation",
            name="int_state",
            field=django_fsm.FSMIntegerField(default=10, protected=True),
        ),
    ]
