# Generated by Django 3.1.7 on 2021-04-12 19:30

from django.db import migrations, models
import evap.evaluation.models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0123_evaluation_state_fsm_int'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailtemplate',
            name='body',
            field=models.TextField(validators=[evap.evaluation.models.validate_template], verbose_name='Plain Text'),
        ),
        migrations.RenameField(
            model_name='emailtemplate',
            old_name='body',
            new_name='plain_content',
        ),
        migrations.AddField(
            model_name='emailtemplate',
            name='html_content',
            field=models.TextField(default='', validators=[evap.evaluation.models.validate_template], verbose_name='HTML'),
            preserve_default=False,
        ),
    ]
