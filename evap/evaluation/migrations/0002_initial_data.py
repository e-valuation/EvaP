from django.db import migrations
from django.contrib.auth.models import Group


def insert_emailtemplates(apps, _schema_editor):
    emailtemplates = [
        ("Lecturer Review Notice", "[EvaP] New Course ready for approval"),
        ("Student Reminder", "[EvaP] Evaluation period is ending"),
        ("Publishing Notice", "[EvaP] A course has been published"),
        ("Login Key Created", "[EvaP] A login key was created"),
    ]

    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, subject in emailtemplates:
        if not EmailTemplate.objects.filter(name=name).exists():
            EmailTemplate.objects.create(name=name, subject=subject, body="")

    Group.objects.create(name="Staff")


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplates),
    ]
