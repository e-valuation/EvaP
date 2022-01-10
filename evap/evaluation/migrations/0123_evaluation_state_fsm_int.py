from django.db import migrations


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
REV_CONVERSION = {val: key for key, val in CONVERSION.items()}


def model_str_to_int(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    for string_type, int_type in CONVERSION.items():
        Evaluation.objects.filter(state=string_type).update(int_state=int_type)


def model_int_to_str(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    for string_type, int_type in CONVERSION.items():
        Evaluation.objects.filter(int_state=int_type).update(state=string_type)


def logentries_str_to_int(apps, _schema_editor):
    LogEntry = apps.get_model("evaluation", "LogEntry")
    for entry in LogEntry.objects.filter(content_type__app_label="evaluation", content_type__model="evaluation"):
        if "state" in entry.data:
            for key in entry.data["state"]:
                entry.data["state"][key] = [
                    CONVERSION[val] if val in CONVERSION else val for val in entry.data["state"][key]
                ]
            entry.save()


def logentries_int_to_str(apps, _schema_editor):
    LogEntry = apps.get_model("evaluation", "LogEntry")
    for entry in LogEntry.objects.filter(content_type__app_label="evaluation", content_type__model="evaluation"):
        if "state" in entry.data:
            for key in entry.data["state"]:
                entry.data["state"][key] = [
                    REV_CONVERSION[val] if val in REV_CONVERSION else val for val in entry.data["state"][key]
                ]
            entry.save()


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0122_prepare_evaluation_state_fsm_int"),
    ]

    operations = [
        migrations.RunPython(model_str_to_int, model_int_to_str),
        migrations.RunPython(logentries_str_to_int, logentries_int_to_str),
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
