from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0026_make_result_counters_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='is_required_for_reward',
            field=models.BooleanField(default=True, verbose_name='is required for reward'),
        ),
    ]
