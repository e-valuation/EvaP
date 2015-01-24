# -*- coding: utf-8 -*-


from django.db import models, migrations
import django_fsm.db.fields.fsmfield
import django.utils.timezone
from django.conf import settings
import evap.evaluation.models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(unique=True, max_length=255, verbose_name='username')),
                ('email', evap.evaluation.models.EmailNullField(max_length=255, unique=True, null=True, verbose_name='email address', blank=True)),
                ('title', models.CharField(max_length=255, null=True, verbose_name='Title', blank=True)),
                ('first_name', models.CharField(max_length=255, null=True, verbose_name='first name', blank=True)),
                ('last_name', models.CharField(max_length=255, null=True, verbose_name='last name', blank=True)),
                ('login_key', models.IntegerField(unique=True, null=True, verbose_name='Login Key', blank=True)),
                ('login_key_valid_until', models.DateField(null=True, verbose_name='Login Key Validity', blank=True)),
                ('cc_users', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='CC Users', blank=True)),
                ('delegates', models.ManyToManyField(related_name='represented_users', verbose_name='Delegates', to=settings.AUTH_USER_MODEL, blank=True)),
                ('groups', models.ManyToManyField(related_query_name='user', related_name='user_set', to='auth.Group', blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of his/her group.', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(related_query_name='user', related_name='user_set', to='auth.Permission', blank=True, help_text='Specific permissions for this user.', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Contribution',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('responsible', models.BooleanField(default=False, verbose_name='responsible')),
                ('can_edit', models.BooleanField(default=False, verbose_name='can edit')),
                ('order', models.IntegerField(default=0, verbose_name='contribution order')),
                ('contributor', models.ForeignKey(related_name='contributions', verbose_name='contributor', blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'ordering': ['order'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('state', django_fsm.db.fields.fsmfield.FSMField(default=b'new', max_length=50)),
                ('name_de', models.CharField(max_length=1024, verbose_name='name (german)')),
                ('name_en', models.CharField(max_length=1024, verbose_name='name (english)')),
                ('kind', models.CharField(max_length=1024, verbose_name='type')),
                ('degree', models.CharField(max_length=1024, verbose_name='degree')),
                ('participant_count', models.IntegerField(default=None, null=True, verbose_name='participant count', blank=True)),
                ('voter_count', models.IntegerField(default=None, null=True, verbose_name='voter count', blank=True)),
                ('vote_start_date', models.DateField(null=True, verbose_name='first date to vote')),
                ('vote_end_date', models.DateField(null=True, verbose_name='last date to vote')),
                ('last_modified_time', models.DateTimeField(auto_now=True)),
                ('last_modified_user', models.ForeignKey(related_name='+', blank=True, to=settings.AUTH_USER_MODEL, null=True)),
                ('participants', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='participants', blank=True)),
            ],
            options={
                'ordering': ('semester', 'degree', 'name_de'),
                'verbose_name': 'course',
                'verbose_name_plural': 'courses',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=1024, verbose_name='Name')),
                ('subject', models.CharField(max_length=1024, verbose_name='Subject', validators=[evap.evaluation.models.validate_template])),
                ('body', models.TextField(verbose_name='Body', validators=[evap.evaluation.models.validate_template])),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='FaqQuestion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order', models.IntegerField(verbose_name='question order')),
                ('question_de', models.TextField(verbose_name='question (german)')),
                ('question_en', models.TextField(verbose_name='question (english)')),
                ('answer_de', models.TextField(verbose_name='answer (german)')),
                ('answer_en', models.TextField(verbose_name='answer (german)')),
            ],
            options={
                'ordering': ['order'],
                'verbose_name': 'question',
                'verbose_name_plural': 'questions',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='FaqSection',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order', models.IntegerField(verbose_name='section order')),
                ('title_de', models.TextField(verbose_name='section title (german)')),
                ('title_en', models.TextField(verbose_name='section title (english)')),
            ],
            options={
                'ordering': ['order'],
                'verbose_name': 'section',
                'verbose_name_plural': 'sections',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='GradeAnswer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('answer', models.IntegerField(verbose_name='answer')),
                ('contribution', models.ForeignKey(to='evaluation.Contribution')),
            ],
            options={
                'verbose_name': 'grade answer',
                'verbose_name_plural': 'grade answers',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='LikertAnswer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('answer', models.IntegerField(verbose_name='answer')),
                ('contribution', models.ForeignKey(to='evaluation.Contribution')),
            ],
            options={
                'verbose_name': 'Likert answer',
                'verbose_name_plural': 'Likert answers',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('text_de', models.TextField(verbose_name='question text (german)')),
                ('text_en', models.TextField(verbose_name='question text (english)')),
                ('kind', models.CharField(max_length=1, verbose_name='kind of question', choices=[('T', 'Text Question'), ('L', 'Likert Question'), ('G', 'Grade Question')])),
            ],
            options={
                'verbose_name': 'question',
                'verbose_name_plural': 'questions',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Questionnaire',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name_de', models.CharField(unique=True, max_length=1024, verbose_name='name (german)')),
                ('name_en', models.CharField(unique=True, max_length=1024, verbose_name='name (english)')),
                ('description_de', models.TextField(null=True, verbose_name='description (german)', blank=True)),
                ('description_en', models.TextField(null=True, verbose_name='description (english)', blank=True)),
                ('public_name_de', models.CharField(max_length=1024, verbose_name='display name (german)')),
                ('public_name_en', models.CharField(max_length=1024, verbose_name='display name (english)')),
                ('teaser_de', models.TextField(null=True, verbose_name='teaser (german)', blank=True)),
                ('teaser_en', models.TextField(null=True, verbose_name='teaser (english)', blank=True)),
                ('index', models.IntegerField(verbose_name='ordering index')),
                ('is_for_contributors', models.BooleanField(default=False, verbose_name='is for contributors')),
                ('obsolete', models.BooleanField(default=False, verbose_name='obsolete')),
            ],
            options={
                'ordering': ('obsolete', 'index', 'name_de'),
                'verbose_name': 'questionnaire',
                'verbose_name_plural': 'questionnaires',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Semester',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name_de', models.CharField(unique=True, max_length=1024, verbose_name='name (german)')),
                ('name_en', models.CharField(unique=True, max_length=1024, verbose_name='name (english)')),
                ('created_at', models.DateField(auto_now_add=True, verbose_name='created at')),
            ],
            options={
                'ordering': ('-created_at', 'name_de'),
                'verbose_name': 'semester',
                'verbose_name_plural': 'semesters',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='TextAnswer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('reviewed_answer', models.TextField(null=True, verbose_name='reviewed answer', blank=True)),
                ('original_answer', models.TextField(verbose_name='original answer', blank=True)),
                ('checked', models.BooleanField(default=False, verbose_name='answer checked')),
                ('hidden', models.BooleanField(default=False, verbose_name='hide answer')),
                ('contribution', models.ForeignKey(to='evaluation.Contribution')),
                ('question', models.ForeignKey(to='evaluation.Question')),
            ],
            options={
                'verbose_name': 'text answer',
                'verbose_name_plural': 'text answers',
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='question',
            name='questionnaire',
            field=models.ForeignKey(to='evaluation.Questionnaire'),
            preserve_default=True,
        ),
        migrations.AlterOrderWithRespectTo(
            name='question',
            order_with_respect_to='questionnaire',
        ),
        migrations.AddField(
            model_name='likertanswer',
            name='question',
            field=models.ForeignKey(to='evaluation.Question'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='gradeanswer',
            name='question',
            field=models.ForeignKey(to='evaluation.Question'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='faqquestion',
            name='section',
            field=models.ForeignKey(related_name='questions', to='evaluation.FaqSection'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='course',
            name='semester',
            field=models.ForeignKey(verbose_name='semester', to='evaluation.Semester'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='course',
            name='voters',
            field=models.ManyToManyField(related_name='+', verbose_name='voters', to=settings.AUTH_USER_MODEL, blank=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='course',
            unique_together=set([('semester', 'degree', 'name_de'), ('semester', 'degree', 'name_en')]),
        ),
        migrations.AddField(
            model_name='contribution',
            name='course',
            field=models.ForeignKey(related_name='contributions', verbose_name='course', to='evaluation.Course'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='contribution',
            name='questionnaires',
            field=models.ManyToManyField(related_name='contributions', verbose_name='questionnaires', to='evaluation.Questionnaire', blank=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='contribution',
            unique_together=set([('course', 'contributor')]),
        ),
    ]
