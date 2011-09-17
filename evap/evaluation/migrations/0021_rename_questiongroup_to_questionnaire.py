# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        db.rename_table('evaluation_questiongroup', 'evaluation_questionnaire')
        db.rename_column('evaluation_course_general_questions', 'questiongroup_id', 'questionnaire_id')
        db.rename_column('evaluation_course_primary_lecturer_questions', 'questiongroup_id', 'questionnaire_id')
        db.rename_column('evaluation_course_secondary_lecturer_questions', 'questiongroup_id', 'questionnaire_id')
        db.rename_column('evaluation_question', 'question_group_id', 'questionnaire_id')
    
    
    def backwards(self, orm):
        db.rename_column('evaluation_question', 'questionnaire_id', 'question_group_id')
        db.rename_column('evaluation_course_secondary_lecturer_questions', 'questionnaire_id', 'questiongroup_id')
        db.rename_column('evaluation_course_primary_lecturer_questions', 'questionnaire_id', 'questiongroup_id')
        db.rename_column('evaluation_course_general_questions', 'questionnaire_id', 'questiongroup_id')
        db.rename_table('evaluation_questionnaire', 'evaluation_questiongroup')
    
    
    models = {
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'evaluation.course': {
            'Meta': {'ordering': "('semester', 'name_de')", 'unique_together': "(('semester', 'name_de'), ('semester', 'name_en'))", 'object_name': 'Course'},
            'general_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'general_courses'", 'blank': 'True', 'to': "orm['evaluation.Questionnaire']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False', 'blank': 'True'}),
            'primary_lecturer_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'primary_courses'", 'blank': 'True', 'to': "orm['evaluation.Questionnaire']"}),
            'primary_lecturers': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'primary_courses'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'secondary_lecturer_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'secondary_courses'", 'blank': 'True', 'to': "orm['evaluation.Questionnaire']"}),
            'secondary_lecturers': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'secondary_courses'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Semester']"}),
            'visible': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'vote_end_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'vote_start_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'voters': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'+'", 'blank': 'True', 'to': "orm['auth.User']"})
        },
        'evaluation.gradeanswer': {
            'Meta': {'object_name': 'GradeAnswer'},
            'answer': ('django.db.models.fields.IntegerField', [], {}),
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'+'", 'to': "orm['evaluation.Course']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lecturer': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': "orm['auth.User']"}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"})
        },
        'evaluation.question': {
            'Meta': {'ordering': "('_order',)", 'object_name': 'Question'},
            '_order': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '1'}),
            'questionnaire': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Questionnaire']"}),
            'text_de': ('django.db.models.fields.TextField', [], {}),
            'text_en': ('django.db.models.fields.TextField', [], {})
        },
        'evaluation.questionnaire': {
            'Meta': {'ordering': "('name_de',)", 'object_name': 'Questionnaire'},
            'description_de': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'description_en': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'obsolete': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'evaluation.semester': {
            'Meta': {'ordering': "('created_at', 'name_de')", 'object_name': 'Semester'},
            'created_at': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'visible': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'evaluation.textanswer': {
            'Meta': {'object_name': 'TextAnswer'},
            'censored_answer': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'checked': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'+'", 'to': "orm['evaluation.Course']"}),
            'hidden': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lecturer': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': "orm['auth.User']"}),
            'original_answer': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'publication_desired': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"})
        },
        'evaluation.userprofile': {
            'Meta': {'object_name': 'UserProfile'},
            'fsr': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'logon_key': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'picture': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'proxies': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'proxied_users'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '30', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['auth.User']", 'unique': 'True'})
        }
    }

    complete_apps = ['evaluation']
