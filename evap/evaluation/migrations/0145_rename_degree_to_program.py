from django.db import migrations, models


def logentries_degrees_to_programs(apps, _schema_editor):
    LogEntry = apps.get_model("evaluation", "LogEntry")
    for entry in LogEntry.objects.filter(content_type__app_label="evaluation", content_type__model="course"):
        if "degrees" in entry.data:
            assert "programs" not in entry.data
            entry.data["programs"] = entry.data.pop("degrees")
            entry.save()


def logentries_programs_to_degrees(apps, _schema_editor):
    LogEntry = apps.get_model("evaluation", "LogEntry")
    for entry in LogEntry.objects.filter(content_type__app_label="evaluation", content_type__model="course"):
        if "programs" in entry.data:
            assert "degrees" not in entry.data
            entry.data["degrees"] = entry.data.pop("programs")
            entry.save()


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0144_alter_evaluation_state"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Degree",
            new_name="Program",
        ),
        migrations.RenameField(
            model_name="course",
            old_name="degrees",
            new_name="programs",
        ),
        migrations.AlterField(
            model_name="course",
            name="programs",
            field=models.ManyToManyField(related_name="courses", to="evaluation.program", verbose_name="programs"),
        ),
        migrations.AlterField(
            model_name="program",
            name="order",
            field=models.IntegerField(default=-1, verbose_name="program order"),
        ),
        migrations.RunPython(logentries_degrees_to_programs, logentries_programs_to_degrees),
    ]
