# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Deleting field 'QuestionGroup.name'
        db.delete_column('evaluation_questiongroup', 'name')

        # Adding field 'QuestionGroup.name_de'
        db.add_column('evaluation_questiongroup', 'name_de', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)

        # Adding field 'QuestionGroup.name_en'
        db.add_column('evaluation_questiongroup', 'name_en', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)

        # Deleting field 'Question.text'
        db.delete_column('evaluation_question', 'text')

        # Adding field 'Question.text_de'
        db.add_column('evaluation_question', 'text_de', self.gf('django.db.models.fields.TextField')(default=''), keep_default=False)

        # Adding field 'Question.text_en'
        db.add_column('evaluation_question', 'text_en', self.gf('django.db.models.fields.TextField')(default=''), keep_default=False)

        # Deleting field 'Semester.name'
        db.delete_column('evaluation_semester', 'name')

        # Adding field 'Semester.name_de'
        db.add_column('evaluation_semester', 'name_de', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)

        # Adding field 'Semester.name_en'
        db.add_column('evaluation_semester', 'name_en', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)

        # Deleting field 'Course.name'
        db.delete_column('evaluation_course', 'name')

        # Adding field 'Course.name_de'
        db.add_column('evaluation_course', 'name_de', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)

        # Adding field 'Course.name_en'
        db.add_column('evaluation_course', 'name_en', self.gf('django.db.models.fields.CharField')(default='', max_length=100), keep_default=False)


    def backwards(self, orm):
        
        # User chose to not deal with backwards NULL issues for 'QuestionGroup.name'
        raise RuntimeError("Cannot reverse this migration. 'QuestionGroup.name' and its values cannot be restored.")

        # Deleting field 'QuestionGroup.name_de'
        db.delete_column('evaluation_questiongroup', 'name_de')

        # Deleting field 'QuestionGroup.name_en'
        db.delete_column('evaluation_questiongroup', 'name_en')

        # User chose to not deal with backwards NULL issues for 'Question.text'
        raise RuntimeError("Cannot reverse this migration. 'Question.text' and its values cannot be restored.")

        # Deleting field 'Question.text_de'
        db.delete_column('evaluation_question', 'text_de')

        # Deleting field 'Question.text_en'
        db.delete_column('evaluation_question', 'text_en')

        # User chose to not deal with backwards NULL issues for 'Semester.name'
        raise RuntimeError("Cannot reverse this migration. 'Semester.name' and its values cannot be restored.")

        # Deleting field 'Semester.name_de'
        db.delete_column('evaluation_semester', 'name_de')

        # Deleting field 'Semester.name_en'
        db.delete_column('evaluation_semester', 'name_en')

        # User chose to not deal with backwards NULL issues for 'Course.name'
        raise RuntimeError("Cannot reverse this migration. 'Course.name' and its values cannot be restored.")

        # Deleting field 'Course.name_de'
        db.delete_column('evaluation_course', 'name_de')

        # Deleting field 'Course.name_en'
        db.delete_column('evaluation_course', 'name_en')


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
            'Meta': {'object_name': 'Course'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False'}),
            'publish_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Semester']"}),
            'vote_end_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'vote_start_date': ('django.db.models.fields.DateField', [], {'null': 'True'})
        },
        'evaluation.gradeanswer': {
            'Meta': {'object_name': 'GradeAnswer'},
            'answer': ('django.db.models.fields.IntegerField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"}),
            'questionnaire': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Questionnaire']"})
        },
        'evaluation.question': {
            'Meta': {'object_name': 'Question'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '1'}),
            'question_group': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.QuestionGroup']"}),
            'text_de': ('django.db.models.fields.TextField', [], {}),
            'text_en': ('django.db.models.fields.TextField', [], {})
        },
        'evaluation.questiongroup': {
            'Meta': {'object_name': 'QuestionGroup'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'evaluation.questionnaire': {
            'Meta': {'object_name': 'Questionnaire'},
            'course': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Course']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'question_group': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.QuestionGroup']"})
        },
        'evaluation.semester': {
            'Meta': {'object_name': 'Semester'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'evaluation.textanswer': {
            'Meta': {'object_name': 'TextAnswer'},
            'answer': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"}),
            'questionnaire': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Questionnaire']"})
        }
    }

    complete_apps = ['evaluation']
