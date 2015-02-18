# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def update_states(apps, schema_editor):
	TextAnswer = apps.get_model("evaluation", "TextAnswer")
	for answer in TextAnswer.objects.all():
		if answer.hidden:
			answer.state = 'hidden'
		elif answer.checked:
			answer.state = 'published'
		else:
			answer.state = 'not_reviewed'
		answer.save()

def backward_update_states(apps, schema_editor):
	TextAnswer = apps.get_model("evaluation", "TextAnswer")
	for answer in TextAnswer.objects.all():
		if answer.state == 'hidden':
			answer.hidden = True
			answer.checked = True
		elif answer.state == 'published':
			answer.hidden = False
			answer.checked = True
		elif answer.state == 'private':
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
