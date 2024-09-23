from django.db import migrations


emailtemplates = [
    ("Grade Reminder", "[EvaP] Notenveröffentlichung für {{semester.name_de}} / Grade publishing for {{semester.name_en}}"),
]


def insert_emailtemplates(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, subject in emailtemplates:
        EmailTemplate.objects.create(name=name, subject=subject, plain_content="", html_content="")


def remove_emailtemplates(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, __ in emailtemplates:
        EmailTemplate.objects.filter(name=name).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0145_rename_degree_to_program'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplates, reverse_code=remove_emailtemplates),
    ]
