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
            ('name_de', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('name_en', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('visible', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('created_at', self.gf('django.db.models.fields.DateField')(auto_now_add=True, blank=True)),
        ))
        db.send_create_signal('evaluation', ['Semester'])

        # Adding model 'Questionnaire'
        db.create_table('evaluation_questionnaire', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name_de', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('name_en', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('description_de', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('description_en', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('teaser_de', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('teaser_en', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('obsolete', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('evaluation', ['Questionnaire'])

        # Adding model 'Course'
        db.create_table('evaluation_course', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('state', self.gf('django_fsm.db.fields.fsmfield.FSMField')(default='new', max_length=50)),
            ('semester', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Semester'])),
            ('name_de', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('name_en', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('kind', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('study', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('vote_start_date', self.gf('django.db.models.fields.DateField')(null=True)),
            ('vote_end_date', self.gf('django.db.models.fields.DateField')(null=True)),
        ))
        db.send_create_signal('evaluation', ['Course'])

        # Adding unique constraint on 'Course', fields ['semester', 'study', 'name_de']
        db.create_unique('evaluation_course', ['semester_id', 'study', 'name_de'])

        # Adding unique constraint on 'Course', fields ['semester', 'study', 'name_en']
        db.create_unique('evaluation_course', ['semester_id', 'study', 'name_en'])

        # Adding M2M table for field participants on 'Course'
        db.create_table('evaluation_course_participants', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('evaluation_course_participants', ['course_id', 'user_id'])

        # Adding M2M table for field voters on 'Course'
        db.create_table('evaluation_course_voters', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('course', models.ForeignKey(orm['evaluation.course'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('evaluation_course_voters', ['course_id', 'user_id'])

        # Adding model 'Assignment'
        db.create_table('evaluation_assignment', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('course', self.gf('django.db.models.fields.related.ForeignKey')(related_name='assignments', to=orm['evaluation.Course'])),
            ('lecturer', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='lecturers', null=True, to=orm['auth.User'])),
        ))
        db.send_create_signal('evaluation', ['Assignment'])

        # Adding M2M table for field questionnaires on 'Assignment'
        db.create_table('evaluation_assignment_questionnaires', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('assignment', models.ForeignKey(orm['evaluation.assignment'], null=False)),
            ('questionnaire', models.ForeignKey(orm['evaluation.questionnaire'], null=False))
        ))
        db.create_unique('evaluation_assignment_questionnaires', ['assignment_id', 'questionnaire_id'])

        # Adding model 'Question'
        db.create_table('evaluation_question', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('questionnaire', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Questionnaire'])),
            ('text_de', self.gf('django.db.models.fields.TextField')()),
            ('text_en', self.gf('django.db.models.fields.TextField')()),
            ('kind', self.gf('django.db.models.fields.CharField')(max_length=1)),
            ('_order', self.gf('django.db.models.fields.IntegerField')(default=0)),
        ))
        db.send_create_signal('evaluation', ['Question'])

        # Adding model 'GradeAnswer'
        db.create_table('evaluation_gradeanswer', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('assignment', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Assignment'])),
            ('answer', self.gf('django.db.models.fields.IntegerField')()),
        ))
        db.send_create_signal('evaluation', ['GradeAnswer'])

        # Adding model 'TextAnswer'
        db.create_table('evaluation_textanswer', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('question', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Question'])),
            ('assignment', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['evaluation.Assignment'])),
            ('censored_answer', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('original_answer', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('checked', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('hidden', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('publication_desired', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('evaluation', ['TextAnswer'])

        # Adding model 'UserProfile'
        db.create_table('evaluation_userprofile', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['auth.User'], unique=True)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=30, null=True, blank=True)),
            ('picture', self.gf('django.db.models.fields.files.ImageField')(max_length=100, null=True, blank=True)),
            ('logon_key', self.gf('django.db.models.fields.IntegerField')(null=True, blank=True)),
            ('logon_key_valid_until', self.gf('django.db.models.fields.DateField')(null=True)),
        ))
        db.send_create_signal('evaluation', ['UserProfile'])

        # Adding M2M table for field proxies on 'UserProfile'
        db.create_table('evaluation_userprofile_proxies', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm['evaluation.userprofile'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('evaluation_userprofile_proxies', ['userprofile_id', 'user_id'])


    def backwards(self, orm):
        
        # Removing unique constraint on 'Course', fields ['semester', 'study', 'name_en']
        db.delete_unique('evaluation_course', ['semester_id', 'study', 'name_en'])

        # Removing unique constraint on 'Course', fields ['semester', 'study', 'name_de']
        db.delete_unique('evaluation_course', ['semester_id', 'study', 'name_de'])

        # Deleting model 'Semester'
        db.delete_table('evaluation_semester')

        # Deleting model 'Questionnaire'
        db.delete_table('evaluation_questionnaire')

        # Deleting model 'Course'
        db.delete_table('evaluation_course')

        # Removing M2M table for field participants on 'Course'
        db.delete_table('evaluation_course_participants')

        # Removing M2M table for field voters on 'Course'
        db.delete_table('evaluation_course_voters')

        # Deleting model 'Assignment'
        db.delete_table('evaluation_assignment')

        # Removing M2M table for field questionnaires on 'Assignment'
        db.delete_table('evaluation_assignment_questionnaires')

        # Deleting model 'Question'
        db.delete_table('evaluation_question')

        # Deleting model 'GradeAnswer'
        db.delete_table('evaluation_gradeanswer')

        # Deleting model 'TextAnswer'
        db.delete_table('evaluation_textanswer')

        # Deleting model 'UserProfile'
        db.delete_table('evaluation_userprofile')

        # Removing M2M table for field proxies on 'UserProfile'
        db.delete_table('evaluation_userprofile_proxies')


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
        'evaluation.assignment': {
            'Meta': {'object_name': 'Assignment'},
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'assignments'", 'to': "orm['evaluation.Course']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lecturer': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'lecturers'", 'null': 'True', 'to': "orm['auth.User']"}),
            'questionnaires': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'assigned_to'", 'blank': 'True', 'to': "orm['evaluation.Questionnaire']"})
        },
        'evaluation.course': {
            'Meta': {'ordering': "('semester', 'study', 'name_de')", 'unique_together': "(('semester', 'study', 'name_de'), ('semester', 'study', 'name_en'))", 'object_name': 'Course'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False', 'blank': 'True'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Semester']"}),
            'state': ('django_fsm.db.fields.fsmfield.FSMField', [], {'default': "'new'", 'max_length': '50'}),
            'study': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'vote_end_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'vote_start_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'voters': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'+'", 'blank': 'True', 'to': "orm['auth.User']"})
        },
        'evaluation.gradeanswer': {
            'Meta': {'object_name': 'GradeAnswer'},
            'answer': ('django.db.models.fields.IntegerField', [], {}),
            'assignment': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Assignment']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
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
            'obsolete': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'teaser_de': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'teaser_en': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'})
        },
        'evaluation.semester': {
            'Meta': {'ordering': "('-created_at', 'name_de')", 'object_name': 'Semester'},
            'created_at': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'visible': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'evaluation.textanswer': {
            'Meta': {'object_name': 'TextAnswer'},
            'assignment': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Assignment']"}),
            'censored_answer': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'checked': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'hidden': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'original_answer': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'publication_desired': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'question': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['evaluation.Question']"})
        },
        'evaluation.userprofile': {
            'Meta': {'object_name': 'UserProfile'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'logon_key': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'logon_key_valid_until': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'picture': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'proxies': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'proxied_users'", 'blank': 'True', 'to': "orm['auth.User']"}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '30', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['auth.User']", 'unique': 'True'})
        }
    }

    complete_apps = ['evaluation']
