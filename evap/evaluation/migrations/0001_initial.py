# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Semester'
        db.create_table(u'evaluation_semester', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name_de', self.gf('django.db.models.fields.CharField')(unique=True, max_length=1024)),
            ('name_en', self.gf('django.db.models.fields.CharField')(unique=True, max_length=1024)),
            ('created_at', self.gf('django.db.models.fields.DateField')(auto_now_add=True, blank=True)),
        ))
        db.send_create_signal(u'evaluation', ['Semester'])

        # Adding model 'Questionnaire'
        db.create_table(u'evaluation_questionnaire', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name_de', self.gf('django.db.models.fields.CharField')(unique=True, max_length=1024)),
            ('name_en', self.gf('django.db.models.fields.CharField')(unique=True, max_length=1024)),
            ('description_de', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('description_en', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('public_name_de', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('public_name_en', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('teaser_de', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('teaser_en', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('index', self.gf('django.db.models.fields.IntegerField')()),
            ('is_for_contributors', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('obsolete', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal(u'evaluation', ['Questionnaire'])

        # Adding model 'Course'
        db.create_table(u'evaluation_course', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('state', self.gf('django_fsm.db.fields.fsmfield.FSMField')(default='new', max_length=50)),
            ('semester', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Semester'])),
            ('name_de', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('name_en', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('kind', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('degree', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('participant_count', self.gf('django.db.models.fields.IntegerField')(default=None, null=True, blank=True)),
            ('voter_count', self.gf('django.db.models.fields.IntegerField')(default=None, null=True, blank=True)),
            ('vote_start_date', self.gf('django.db.models.fields.DateField')(null=True)),
            ('vote_end_date', self.gf('django.db.models.fields.DateField')(null=True)),
            ('last_modified_time', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, blank=True)),
            ('last_modified_user', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='+', null=True, to=orm['auth.User'])),
        ))
        db.send_create_signal(u'evaluation', ['Course'])

        # Adding unique constraint on 'Course', fields ['semester', 'degree', 'name_de']
        db.create_unique(u'evaluation_course', ['semester_id', 'degree', 'name_de'])

        # Adding unique constraint on 'Course', fields ['semester', 'degree', 'name_en']
        db.create_unique(u'evaluation_course', ['semester_id', 'degree', 'name_en'])

        # Adding M2M table for field participants on 'Course'
        m2m_table_name = db.shorten_name(u'evaluation_course_participants')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm[u'evaluation.course'], null=False)),
            ('user', models.ForeignKey(orm[u'auth.user'], null=False))
        ))
        db.create_unique(m2m_table_name, ['course_id', 'user_id'])

        # Adding M2M table for field voters on 'Course'
        m2m_table_name = db.shorten_name(u'evaluation_course_voters')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm[u'evaluation.course'], null=False)),
            ('user', models.ForeignKey(orm[u'auth.user'], null=False))
        ))
        db.create_unique(m2m_table_name, ['course_id', 'user_id'])

        # Adding model 'Contribution'
        db.create_table(u'evaluation_contribution', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('course', self.gf('django.db.models.fields.related.ForeignKey')(related_name='contributions', to=orm['evaluation.Course'])),
            ('contributor', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='contributors', null=True, to=orm['auth.User'])),
            ('responsible', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('can_edit', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal(u'evaluation', ['Contribution'])

        # Adding unique constraint on 'Contribution', fields ['course', 'contributor']
        db.create_unique(u'evaluation_contribution', ['course_id', 'contributor_id'])

        # Adding M2M table for field questionnaires on 'Contribution'
        m2m_table_name = db.shorten_name(u'evaluation_contribution_questionnaires')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('contribution', models.ForeignKey(orm[u'evaluation.contribution'], null=False)),
            ('questionnaire', models.ForeignKey(orm[u'evaluation.questionnaire'], null=False))
        ))
        db.create_unique(m2m_table_name, ['contribution_id', 'questionnaire_id'])

        # Adding model 'Question'
        db.create_table(u'evaluation_question', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('questionnaire', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Questionnaire'])),
            ('text_de', self.gf('django.db.models.fields.TextField')()),
            ('text_en', self.gf('django.db.models.fields.TextField')()),
            ('kind', self.gf('django.db.models.fields.CharField')(max_length=1)),
            ('_order', self.gf('django.db.models.fields.IntegerField')(default=0)),
        ))
        db.send_create_signal(u'evaluation', ['Question'])

        # Adding model 'GradeAnswer'
        db.create_table(u'evaluation_gradeanswer', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('contribution', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Contribution'])),
            ('answer', self.gf('django.db.models.fields.IntegerField')()),
        ))
        db.send_create_signal(u'evaluation', ['GradeAnswer'])

        # Adding model 'TextAnswer'
        db.create_table(u'evaluation_textanswer', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('contribution', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Contribution'])),
            ('reviewed_answer', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('original_answer', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('checked', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('hidden', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal(u'evaluation', ['TextAnswer'])

        # Adding model 'FaqSection'
        db.create_table(u'evaluation_faqsection', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('order', self.gf('django.db.models.fields.IntegerField')()),
            ('title_de', self.gf('django.db.models.fields.TextField')()),
            ('title_en', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal(u'evaluation', ['FaqSection'])

        # Adding model 'FaqQuestion'
        db.create_table(u'evaluation_faqquestion', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('section', self.gf('django.db.models.fields.related.ForeignKey')(related_name='questions', to=orm['evaluation.FaqSection'])),
            ('order', self.gf('django.db.models.fields.IntegerField')()),
            ('question_de', self.gf('django.db.models.fields.TextField')()),
            ('question_en', self.gf('django.db.models.fields.TextField')()),
            ('answer_de', self.gf('django.db.models.fields.TextField')()),
            ('answer_en', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal(u'evaluation', ['FaqQuestion'])

        # Adding model 'UserProfile'
        db.create_table(u'evaluation_userprofile', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['auth.User'], unique=True)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=1024, null=True, blank=True)),
            ('picture', self.gf('django.db.models.fields.files.ImageField')(max_length=100, null=True, blank=True)),
            ('login_key', self.gf('django.db.models.fields.IntegerField')(null=True, blank=True)),
            ('login_key_valid_until', self.gf('django.db.models.fields.DateField')(null=True)),
        ))
        db.send_create_signal(u'evaluation', ['UserProfile'])

        # Adding M2M table for field delegates on 'UserProfile'
        m2m_table_name = db.shorten_name(u'evaluation_userprofile_delegates')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm[u'evaluation.userprofile'], null=False)),
            ('user', models.ForeignKey(orm[u'auth.user'], null=False))
        ))
        db.create_unique(m2m_table_name, ['userprofile_id', 'user_id'])

        # Adding M2M table for field cc_users on 'UserProfile'
        m2m_table_name = db.shorten_name(u'evaluation_userprofile_cc_users')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm[u'evaluation.userprofile'], null=False)),
            ('user', models.ForeignKey(orm[u'auth.user'], null=False))
        ))
        db.create_unique(m2m_table_name, ['userprofile_id', 'user_id'])


    def backwards(self, orm):
        # Removing unique constraint on 'Contribution', fields ['course', 'contributor']
        db.delete_unique(u'evaluation_contribution', ['course_id', 'contributor_id'])

        # Removing unique constraint on 'Course', fields ['semester', 'degree', 'name_en']
        db.delete_unique(u'evaluation_course', ['semester_id', 'degree', 'name_en'])

        # Removing unique constraint on 'Course', fields ['semester', 'degree', 'name_de']
        db.delete_unique(u'evaluation_course', ['semester_id', 'degree', 'name_de'])

        # Deleting model 'Semester'
        db.delete_table(u'evaluation_semester')

        # Deleting model 'Questionnaire'
        db.delete_table(u'evaluation_questionnaire')

        # Deleting model 'Course'
        db.delete_table(u'evaluation_course')

        # Removing M2M table for field participants on 'Course'
        db.delete_table(db.shorten_name(u'evaluation_course_participants'))

        # Removing M2M table for field voters on 'Course'
        db.delete_table(db.shorten_name(u'evaluation_course_voters'))

        # Deleting model 'Contribution'
        db.delete_table(u'evaluation_contribution')

        # Removing M2M table for field questionnaires on 'Contribution'
        db.delete_table(db.shorten_name(u'evaluation_contribution_questionnaires'))

        # Deleting model 'Question'
        db.delete_table(u'evaluation_question')

        # Deleting model 'GradeAnswer'
        db.delete_table(u'evaluation_gradeanswer')

        # Deleting model 'TextAnswer'
        db.delete_table(u'evaluation_textanswer')

        # Deleting model 'FaqSection'
        db.delete_table(u'evaluation_faqsection')

        # Deleting model 'FaqQuestion'
        db.delete_table(u'evaluation_faqquestion')

        # Deleting model 'UserProfile'
        db.delete_table(u'evaluation_userprofile')

        # Removing M2M table for field delegates on 'UserProfile'
        db.delete_table(db.shorten_name(u'evaluation_userprofile_delegates'))

        # Removing M2M table for field cc_users on 'UserProfile'
        db.delete_table(db.shorten_name(u'evaluation_userprofile_cc_users'))


    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')", 'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Group']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Permission']"}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'evaluation.contribution': {
            'Meta': {'unique_together': "(('course', 'contributor'),)", 'object_name': 'Contribution'},
            'can_edit': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contributor': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'contributors'", 'null': 'True', 'to': u"orm['auth.User']"}),
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'contributions'", 'to': u"orm['evaluation.Course']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'questionnaires': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'assigned_to'", 'blank': 'True', 'to': u"orm['evaluation.Questionnaire']"}),
            'responsible': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        u'evaluation.course': {
            'Meta': {'ordering': "('semester', 'degree', 'name_de')", 'unique_together': "(('semester', 'degree', 'name_de'), ('semester', 'degree', 'name_en'))", 'object_name': 'Course'},
            'degree': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'last_modified_time': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'last_modified_user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': u"orm['auth.User']"}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'participant_count': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.User']", 'symmetrical': 'False', 'blank': 'True'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Semester']"}),
            'state': ('django_fsm.db.fields.fsmfield.FSMField', [], {'default': "'new'", 'max_length': '50'}),
            'vote_end_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'vote_start_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'voter_count': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'voters': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'+'", 'blank': 'True', 'to': u"orm['auth.User']"})
        },
        u'evaluation.faqquestion': {
            'Meta': {'ordering': "['order']", 'object_name': 'FaqQuestion'},
            'answer_de': ('django.db.models.fields.TextField', [], {}),
            'answer_en': ('django.db.models.fields.TextField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'order': ('django.db.models.fields.IntegerField', [], {}),
            'question_de': ('django.db.models.fields.TextField', [], {}),
            'question_en': ('django.db.models.fields.TextField', [], {}),
            'section': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'questions'", 'to': u"orm['evaluation.FaqSection']"})
        },
        u'evaluation.faqsection': {
            'Meta': {'ordering': "['order']", 'object_name': 'FaqSection'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'order': ('django.db.models.fields.IntegerField', [], {}),
            'title_de': ('django.db.models.fields.TextField', [], {}),
            'title_en': ('django.db.models.fields.TextField', [], {})
        },
        u'evaluation.gradeanswer': {
            'Meta': {'object_name': 'GradeAnswer'},
            'answer': ('django.db.models.fields.IntegerField', [], {}),
            'contribution': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Contribution']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Question']"})
        },
        u'evaluation.question': {
            'Meta': {'ordering': "(u'_order',)", 'object_name': 'Question'},
            '_order': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '1'}),
            'questionnaire': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Questionnaire']"}),
            'text_de': ('django.db.models.fields.TextField', [], {}),
            'text_en': ('django.db.models.fields.TextField', [], {})
        },
        u'evaluation.questionnaire': {
            'Meta': {'ordering': "('obsolete', 'index', 'name_de')", 'object_name': 'Questionnaire'},
            'description_de': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'description_en': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'index': ('django.db.models.fields.IntegerField', [], {}),
            'is_for_contributors': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'obsolete': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'public_name_de': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'public_name_en': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'teaser_de': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'teaser_en': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'})
        },
        u'evaluation.semester': {
            'Meta': {'ordering': "('-created_at', 'name_de')", 'object_name': 'Semester'},
            'created_at': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'})
        },
        u'evaluation.textanswer': {
            'Meta': {'object_name': 'TextAnswer'},
            'checked': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contribution': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Contribution']"}),
            'hidden': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'original_answer': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Question']"}),
            'reviewed_answer': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'})
        },
        u'evaluation.userprofile': {
            'Meta': {'object_name': 'UserProfile'},
            'cc_users': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'cc_users'", 'blank': 'True', 'to': u"orm['auth.User']"}),
            'delegates': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'represented_users'", 'blank': 'True', 'to': u"orm['auth.User']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'login_key': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'login_key_valid_until': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'picture': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '1024', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['auth.User']", 'unique': 'True'})
        }
    }

    complete_apps = ['evaluation']