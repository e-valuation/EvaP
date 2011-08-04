# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'Semester'
        db.create_table('evaluation_semester', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
        ))
        db.send_create_signal('evaluation', ['Semester'])

        # Adding model 'Course'
        db.create_table('evaluation_course', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('semester', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Semester'])),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
        ))
        db.send_create_signal('evaluation', ['Course'])

        # Adding M2M table for field participants on 'Course'
        db.create_table('evaluation_course_participants', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('evaluation_course_participants', ['course_id', 'user_id'])

        # Adding model 'QuestionGroup'
        db.create_table('evaluation_questiongroup', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
        ))
        db.send_create_signal('evaluation', ['QuestionGroup'])

        # Adding model 'Question'
        db.create_table('evaluation_question', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question_group', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.QuestionGroup'])),
            ('text', self.gf('django.db.models.fields.TextField')()),
            ('kind', self.gf('django.db.models.fields.CharField')(max_length=1)),
        ))
        db.send_create_signal('evaluation', ['Question'])

        # Adding model 'Questionnaire'
        db.create_table('evaluation_questionnaire', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('course', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Course'])),
            ('question_group', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.QuestionGroup'])),
        ))
        db.send_create_signal('evaluation', ['Questionnaire'])

        # Adding model 'GradeAnswer'
        db.create_table('evaluation_gradeanswer', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('questionnaire', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Questionnaire'])),
            ('answer', self.gf('django.db.models.fields.IntegerField')()),
        ))
        db.send_create_signal('evaluation', ['GradeAnswer'])

        # Adding model 'TextAnswer'
        db.create_table('evaluation_textanswer', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('questionnaire', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Questionnaire'])),
            ('answer', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal('evaluation', ['TextAnswer'])


    def backwards(self, orm):
        
        # Deleting model 'Semester'
        db.delete_table('evaluation_semester')

        # Deleting model 'Course'
        db.delete_table('evaluation_course')

        # Removing M2M table for field participants on 'Course'
        db.delete_table('evaluation_course_participants')

        # Deleting model 'QuestionGroup'
        db.delete_table('evaluation_questiongroup')

        # Deleting model 'Question'
        db.delete_table('evaluation_question')

        # Deleting model 'Questionnaire'
        db.delete_table('evaluation_questionnaire')

        # Deleting model 'GradeAnswer'
        db.delete_table('evaluation_gradeanswer')

        # Deleting model 'TextAnswer'
        db.delete_table('evaluation_textanswer')


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
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Semester']"})
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
            'text': ('django.db.models.fields.TextField', [], {})
        },
        'evaluation.questiongroup': {
            'Meta': {'object_name': 'QuestionGroup'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
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
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
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
