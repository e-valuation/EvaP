# Generated by Django 2.0.5 on 2018-05-08 17:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0065_questionnaire_type'),
    ]

    operations = [

        migrations.RenameField(
            model_name='course',
            old_name='is_required_for_reward',
            new_name='is_rewarded',
        ),

        migrations.AlterField(
            model_name='course',
            name='is_rewarded',
            field=models.BooleanField(default=True, verbose_name='is rewarded')
        ),
    ]
