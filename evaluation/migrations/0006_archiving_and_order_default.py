# -*- coding: utf-8 -*-


from django.db import models, migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0005_auto_20150115_1717'),
    ]

    operations = [
        migrations.RenameField(
            model_name='course',
            old_name='participant_count',
            new_name='_participant_count',
        ),
        migrations.RenameField(
            model_name='course',
            old_name='voter_count',
            new_name='_voter_count',
        ),
        migrations.AlterField(
            model_name='course',
            name='last_modified_user',
            field=models.ForeignKey(related_name='+', on_delete=django.db.models.deletion.SET_NULL, blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        # these are not related to archiving, but are leftover from a previou commit
        migrations.AlterField(
            model_name='contribution',
            name='order',
            field=models.IntegerField(default=-1, verbose_name='contribution order'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='faqquestion',
            name='order',
            field=models.IntegerField(default=-1, verbose_name='question order'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='faqsection',
            name='order',
            field=models.IntegerField(default=-1, verbose_name='section order'),
            preserve_default=True,
        ),
    ]
