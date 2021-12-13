from django.db import migrations

TEMPLATE_NAME = "Text Answer Review Reminder"
TEMPLATE_SUBJECT = "[EvaP] Bitte Textantworten reviewen / Please review text answers"


def insert_emailtemplate(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.create(name=TEMPLATE_NAME, subject=TEMPLATE_SUBJECT, plain_content="", html_content="")


def remove_emailtemplate(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.filter(name=TEMPLATE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0125_use_lists_for_ordering'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplate, reverse_code=remove_emailtemplate),
    ]
