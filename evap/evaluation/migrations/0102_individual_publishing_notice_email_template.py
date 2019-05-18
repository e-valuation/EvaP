from django.db import migrations

TEMPLATE_NAME_OLD = "Publishing Notice"
TEMPLATE_NAME_CONTRIBUTOR = "Publishing Notice Contributor"
TEMPLATE_NAME_PARTICIPANT = "Publishing Notice Participant"
TEMPLATE_SUBJECT = "[EvaP] Evaluierungsergebnisse veröffentlicht / Evaluation results published"


def insert_participant_email_template(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.filter(name=TEMPLATE_NAME_OLD).update(name=TEMPLATE_NAME_CONTRIBUTOR)
    EmailTemplate.objects.create(name=TEMPLATE_NAME_PARTICIPANT, subject=TEMPLATE_SUBJECT, body="")


def remove_participant_email_template(apps, _schema_editor):
    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.get(name=TEMPLATE_NAME_CONTRIBUTOR).update(name=TEMPLATE_NAME_OLD)
    EmailTemplate.objects.filter(name=TEMPLATE_NAME_PARTICIPANT).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('evaluation', '0101_evaluation_weight'),
    ]

    operations = [
        migrations.RunPython(
            insert_participant_email_template,
            reverse_code=remove_participant_email_template
        ),
    ]
