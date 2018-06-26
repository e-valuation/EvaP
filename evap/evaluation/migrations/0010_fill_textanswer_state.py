from django.db import migrations


def update_states(apps, _schema_editor):
    TextAnswer = apps.get_model("evaluation", "TextAnswer")
    for answer in TextAnswer.objects.all():
        if answer.hidden:
            answer.state = 'HI'
        elif answer.checked:
            answer.state = 'PU'
        else:
            answer.state = 'NR'
        answer.save()


def backward_update_states(apps, _schema_editor):
    TextAnswer = apps.get_model("evaluation", "TextAnswer")
    for answer in TextAnswer.objects.all():
        if answer.state == 'HI':
            answer.hidden = True
            answer.checked = True
        elif answer.state == 'PU':
            answer.hidden = False
            answer.checked = True
        elif answer.state == 'PR':
            answer.hidden = False
            answer.checked = True
        else:
            answer.hidden = True
            answer.checked = False
        answer.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0009_add_textanswer_state'),
    ]

    operations = [
        migrations.RunPython(update_states, backward_update_states),
    ]
