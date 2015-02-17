# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def update_states(apps, schema_editor):
	TextAnswer = apps.get_model("evaluation", "TextAnswer")
	for answer in TextAnswer.objects.all():
		if answer.hidden:
			answer.state = 'N'
		elif answer.checked:
			answer.state = 'Y'
		else:
			answer.state = ''
		answer.save()

def backward_update_states(apps, schema_editor):
	TextAnswer = apps.get_model("evaluation", "TextAnswer")
	for answer in TextAnswer.objects.all():
		if answer.state == 'N':
			answer.hidden = True
			answer.checked = True
		elif answer.state == 'Y':
			answer.hidden = False
			answer.checked = True
		elif answer.state == 'P':
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
