# -*- coding: utf-8 -*-


from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0002_initial_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='is_graded',
            field=models.BooleanField(default=True, verbose_name='is graded'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='cc_users',
            field=models.ManyToManyField(related_name='ccing_users', verbose_name='CC Users', to=settings.AUTH_USER_MODEL, blank=True),
            preserve_default=True,
        ),
    ]
