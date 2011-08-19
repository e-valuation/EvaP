# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Deleting model 'Questionnaire'
        db.delete_table('evaluation_questionnaire')

        # Deleting field 'TextAnswer.questionnaire'
        db.delete_column('evaluation_textanswer', 'questionnaire_id')

        # Adding field 'TextAnswer.course'
        db.add_column('evaluation_textanswer', 'course', self.gf('django.db.models.fields.related.ForeignKey')(default=0, related_name='+', to=orm['evaluation.Course']), keep_default=False)

        # Adding field 'TextAnswer.lecturer'
        db.add_column('evaluation_textanswer', 'lecturer', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='+', null=True, to=orm['auth.User']), keep_default=False)

        # Deleting field 'GradeAnswer.questionnaire'
        db.delete_column('evaluation_gradeanswer', 'questionnaire_id')

        # Adding field 'GradeAnswer.course'
        db.add_column('evaluation_gradeanswer', 'course', self.gf('django.db.models.fields.related.ForeignKey')(default=0, related_name='+', to=orm['evaluation.Course']), keep_default=False)

        # Adding field 'GradeAnswer.lecturer'
        db.add_column('evaluation_gradeanswer', 'lecturer', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='+', null=True, to=orm['auth.User']), keep_default=False)

        # Adding M2M table for field general_questions on 'Course'
        db.create_table('evaluation_course_general_questions', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('questiongroup', models.ForeignKey(orm['evaluation.questiongroup'], null=False))
        ))
        db.create_unique('evaluation_course_general_questions', ['course_id', 'questiongroup_id'])

        # Adding M2M table for field primary_lectuerer_questions on 'Course'
        db.create_table('evaluation_course_primary_lectuerer_questions', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('questiongroup', models.ForeignKey(orm['evaluation.questiongroup'], null=False))
        ))
        db.create_unique('evaluation_course_primary_lectuerer_questions', ['course_id', 'questiongroup_id'])

        # Adding M2M table for field secondary_lecturer_questions on 'Course'
        db.create_table('evaluation_course_secondary_lecturer_questions', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('questiongroup', models.ForeignKey(orm['evaluation.questiongroup'], null=False))
        ))
        db.create_unique('evaluation_course_secondary_lecturer_questions', ['course_id', 'questiongroup_id'])


    def backwards(self, orm):
        
        # Adding model 'Questionnaire'
        db.create_table('evaluation_questionnaire', (
            ('lecturer', self.gf('django.db.models.fields.related.ForeignKey')(related_name='+', null=True, to=orm['auth.User'], blank=True)),
            ('course', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Course'])),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question_group', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.QuestionGroup'])),
        ))
        db.send_create_signal('evaluation', ['Questionnaire'])

        # User chose to not deal with backwards NULL issues for 'TextAnswer.questionnaire'
        raise RuntimeError("Cannot reverse this migration. 'TextAnswer.questionnaire' and its values cannot be restored.")

        # Deleting field 'TextAnswer.course'
        db.delete_column('evaluation_textanswer', 'course_id')

        # Deleting field 'TextAnswer.lecturer'
        db.delete_column('evaluation_textanswer', 'lecturer_id')

        # User chose to not deal with backwards NULL issues for 'GradeAnswer.questionnaire'
        raise RuntimeError("Cannot reverse this migration. 'GradeAnswer.questionnaire' and its values cannot be restored.")

        # Deleting field 'GradeAnswer.course'
        db.delete_column('evaluation_gradeanswer', 'course_id')

        # Deleting field 'GradeAnswer.lecturer'
        db.delete_column('evaluation_gradeanswer', 'lecturer_id')

        # Removing M2M table for field general_questions on 'Course'
        db.delete_table('evaluation_course_general_questions')

        # Removing M2M table for field primary_lectuerer_questions on 'Course'
        db.delete_table('evaluation_course_primary_lectuerer_questions')

        # Removing M2M table for field secondary_lecturer_questions on 'Course'
        db.delete_table('evaluation_course_secondary_lecturer_questions')


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
            'general_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'general_courses'", 'blank': 'True', 'to': "orm['evaluation.QuestionGroup']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False', 'blank': 'True'}),
            'primary_lectuerer_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'primary_courses'", 'blank': 'True', 'to': "orm['evaluation.QuestionGroup']"}),
            'primary_lecturers': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'primary_courses'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'publish_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'secondary_lecturer_questions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'secondary_courses'", 'blank': 'True', 'to': "orm['evaluation.QuestionGroup']"}),
            'secondary_lecturers': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'secondary_courses'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Semester']"}),
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
            'question_group': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.QuestionGroup']"}),
            'text_de': ('django.db.models.fields.TextField', [], {}),
            'text_en': ('django.db.models.fields.TextField', [], {})
        },
        'evaluation.questiongroup': {
            'Meta': {'object_name': 'QuestionGroup'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
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
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'+'", 'to': "orm['evaluation.Course']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lecturer': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': "orm['auth.User']"}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"})
        }
    }

    complete_apps = ['evaluation']
