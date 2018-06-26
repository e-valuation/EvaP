from django.db import migrations


emailtemplates = [
    ("Editor Review Reminder", "[EvaP] Reminder: Neue Lehrveranstaltungen stehen zur Überprüfung bereit / New Course ready for approval"),
]


def insert_emailtemplates(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, subject in emailtemplates:
        EmailTemplate.objects.create(name=name, subject=subject, body="")


def remove_emailtemplates(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, subject in emailtemplates:
        EmailTemplate.objects.filter(name=name).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0060_change_text_fields_to_char_fields'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplates, reverse_code=remove_emailtemplates),
    ]
