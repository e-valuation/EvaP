# -*- coding: utf-8 -*-


from django.db import models, migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RewardPointGranting',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('granting_time', models.DateTimeField(auto_now_add=True, verbose_name='granting time')),
                ('value', models.IntegerField(default=0, verbose_name='value')),
                ('semester', models.ForeignKey(related_name='reward_point_grantings', blank=True, to='evaluation.Semester', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('user_profile', models.ForeignKey(related_name='reward_point_grantings', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='RewardPointRedemption',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('redemption_time', models.DateTimeField(auto_now_add=True, verbose_name='redemption time')),
                ('value', models.IntegerField(default=0, verbose_name='value')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='RewardPointRedemptionEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=1024, verbose_name='event name')),
                ('date', models.DateField(verbose_name='event date')),
                ('redeem_end_date', models.DateField(verbose_name='redemption end date')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SemesterActivation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=False)),
                ('semester', models.ForeignKey(related_name='rewards_active', to='evaluation.Semester', unique=True, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='rewardpointredemption',
            name='event',
            field=models.ForeignKey(related_name='reward_point_redemptions', to='rewards.RewardPointRedemptionEvent', on_delete=django.db.models.deletion.CASCADE),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='rewardpointredemption',
            name='user_profile',
            field=models.ForeignKey(related_name='reward_point_redemptions', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE),
            preserve_default=True,
        ),
    ]
