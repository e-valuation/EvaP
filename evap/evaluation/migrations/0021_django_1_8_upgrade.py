from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0020_change_vote_date_texts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='groups',
            field=models.ManyToManyField(related_name='user_set', to='auth.Group', blank=True, related_query_name='user', verbose_name='groups', help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.'),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='last_login',
            field=models.DateTimeField(blank=True, verbose_name='last login', null=True),
        ),
    ]
