# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'FaqQuestion'
        db.create_table(u'evaluation_faqquestion', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('section', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.FaqSection'])),
            ('order', self.gf('django.db.models.fields.IntegerField')()),
            ('question_de', self.gf('django.db.models.fields.TextField')()),
            ('question_en', self.gf('django.db.models.fields.TextField')()),
            ('answer_de', self.gf('django.db.models.fields.TextField')()),
            ('answer_en', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal(u'evaluation', ['FaqQuestion'])

        # Adding model 'FaqSection'
        db.create_table(u'evaluation_faqsection', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('order', self.gf('django.db.models.fields.IntegerField')()),
            ('title_de', self.gf('django.db.models.fields.TextField')()),
            ('title_en', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal(u'evaluation', ['FaqSection'])


    def backwards(self, orm):
        # Deleting model 'FaqQuestion'
        db.delete_table(u'evaluation_faqquestion')

        # Deleting model 'FaqSection'
        db.delete_table(u'evaluation_faqsection')


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
            'degree': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'last_modified_time': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'last_modified_user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': u"orm['auth.User']"}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '140'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '140'}),
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
            'section': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.FaqSection']"})
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
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'obsolete': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'public_name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'public_name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'teaser_de': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'teaser_en': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'})
        },
        u'evaluation.semester': {
            'Meta': {'ordering': "('-created_at', 'name_de')", 'object_name': 'Semester'},
            'created_at': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
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
            'delegates': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'represented_users'", 'blank': 'True', 'to': u"orm['auth.User']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'login_key': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'login_key_valid_until': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'picture': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '30', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['auth.User']", 'unique': 'True'})
        }
    }

    complete_apps = ['evaluation']