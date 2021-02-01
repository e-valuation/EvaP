from django.db import migrations
import django_fsm


# as defined in the Evaluation model
class State:
    NEW = 10
    PREPARED = 20
    EDITOR_APPROVED = 30
    APPROVED = 40
    IN_EVALUATION = 50
    EVALUATED = 60
    REVIEWED = 70
    PUBLISHED = 80


CONVERSION = {
    "new": State.NEW,
    "prepared": State.PREPARED,
    "editor_approved": State.EDITOR_APPROVED,
    "approved": State.APPROVED,
    "in_evaluation": State.IN_EVALUATION,
    "evaluated": State.EVALUATED,
    "reviewed": State.REVIEWED,
    "published": State.PUBLISHED,
}


def str_to_int(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    for string_type, int_type in CONVERSION.items():
        Evaluation.objects.filter(state=string_type).update(int_state=int_type)


def int_to_str(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    for string_type, int_type in CONVERSION.items():
        Evaluation.objects.filter(int_state=int_type).update(state=string_type)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0121_prepare_evaluation_state_fsm_int'),
    ]

    operations = [
        migrations.RunPython(str_to_int, int_to_str),
        migrations.RemoveField(
            model_name="evaluation",
            name="state",
        ),
        migrations.RenameField(
            model_name="evaluation",
            old_name="int_state",
            new_name="state",
        ),
    ]
