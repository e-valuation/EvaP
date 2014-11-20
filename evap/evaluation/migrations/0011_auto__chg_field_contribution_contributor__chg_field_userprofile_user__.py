# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):


        staff_group = orm["auth.Group"].objects.create(name="Staff")
        # do not use orm here. we want the new userprofile.

        for user in orm["auth.User"].objects.all():
            if user.is_staff:
                user.groups.add(staff_group)


        # rename old userprofile table and create new one
        db.rename_table("evaluation_userprofile", "evaluation_olduserprofile")
        db.create_table(u'evaluation_userprofile', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('password', self.gf('django.db.models.fields.CharField')(max_length=128)),
            ('last_login', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now)),
            ('username', self.gf('django.db.models.fields.CharField')(unique=True, max_length=255)),
            ('email', self.gf('django.db.models.fields.EmailField')(max_length=255, null=True, blank=True)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=255, null=True, blank=True)),
            ('first_name', self.gf('django.db.models.fields.CharField')(max_length=255, null=True, blank=True)),
            ('last_name', self.gf('django.db.models.fields.CharField')(max_length=255, null=True, blank=True)),
            ('login_key', self.gf('django.db.models.fields.IntegerField')(null=True, blank=True)),
            ('login_key_valid_until', self.gf('django.db.models.fields.DateField')(null=True)),
            ('is_superuser', self.gf('django.db.models.fields.BooleanField')()),
        ))
        db.send_create_signal(u'evaluation', ['UserProfile'])

        # populate new userprofile table
        userprofiletable_sql = ("INSERT INTO evaluation_userprofile "
            "(SELECT u.id, password, last_login, username, email, title, first_name, last_name, login_key, login_key_valid_until, is_superuser "
            "FROM auth_user as u INNER JOIN evaluation_olduserprofile as p ON u.id = p.user_id)")
        db.execute(userprofiletable_sql)

        # adjust userprofile primary key sequence
        db.execute("SELECT setval('evaluation_userprofile_id_seq', ( SELECT MAX(id) FROM evaluation_userprofile)+1)")


        def rename_column_update_ids(table, old_name, new_name):
            db.drop_foreign_key(table, old_name)
            db.execute("UPDATE {0} as d SET {1} = (SELECT user_id FROM evaluation_olduserprofile WHERE id=d.{1})"
                .format(table, old_name))
            db.rename_column(table, old_name, new_name)
            db.alter_column(table, new_name, models.ForeignKey(to=orm['evaluation.Userprofile']))

        # update Userprofile delegates
        rename_column_update_ids('evaluation_userprofile_delegates', 'userprofile_id', 'from_userprofile_id')
        db.rename_column('evaluation_userprofile_delegates', 'user_id', 'to_userprofile_id')

        # update Userprofile cc users
        rename_column_update_ids('evaluation_userprofile_cc_users', 'userprofile_id', 'from_userprofile_id')
        db.rename_column('evaluation_userprofile_cc_users', 'user_id', 'to_userprofile_id')
        

        def rename_column(table_name, old_column_name, new_column_name):
            db.drop_foreign_key(table_name, old_column_name)
            db.rename_column(table_name, old_column_name, new_column_name)
            db.alter_column(table_name, new_column_name, models.ForeignKey(to=orm['evaluation.Userprofile']))

        rename_column('evaluation_course_participants', 'user_id', 'userprofile_id')
        
        rename_column('evaluation_course_voters', 'user_id', 'userprofile_id')



        # Changing field 'Contribution.contributor'
        #db.drop_foreign_key("evaluation_contribution", "contributor_id")
        db.alter_column(u'evaluation_contribution', 'contributor_id', self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['evaluation.UserProfile']))
        #db.alter_column("evaluation_contribution", "contributor_id", models.ForeignKey(to=orm['evaluation.Userprofile'], null=True))

        # Changing field 'UserProfile.user'
        #db.alter_column(u'evaluation_userprofile', 'user_id', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['evaluation.UserProhfile'], unique=True))

        # Changing field 'Course.last_modified_user'
        #db.drop_foreign_key("evaluation_course", "last_modified_user_id")
        db.alter_column(u'evaluation_course', 'last_modified_user_id', self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['evaluation.UserProfile']))
        #db.alter_column("evaluation_course", "last_modified_user_id", models.ForeignKey(to=orm['evaluation.Userprofile'], null=True))


        def rename_table_and_column(old_table_name, new_table_name, old_column_name, new_column_name):
            #db.drop_foreign_key(old_table_name, old_column_name)
            db.rename_column(old_table_name, old_column_name, new_column_name)
            db.rename_table(old_table_name, new_table_name)
            #db.alter_column(new_table_name, new_column_name, models.ForeignKey(to=orm['evaluation.Userprofile']))

        rename_table_and_column("auth_user_groups", "evaluation_userprofile_groups", "user_id", "userprofile_id")
        rename_table_and_column("auth_user_user_permissions", "evaluation_userprofile_user_permissions", "user_id", "userprofile_id")

        # this is necessary, otherwise the table deletions throw errors
        db.commit_transaction()
        db.start_transaction()

        db.delete_table("evaluation_olduserprofile")
        db.delete_table("auth_user")


    def backwards(self, orm):
        raise NotImplementedError()


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
            'Meta': {'ordering': "['order']", 'unique_together': "(('course', 'contributor'),)", 'object_name': 'Contribution'},
            'can_edit': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contributor': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'contributions'", 'null': 'True', 'to': u"orm['evaluation.UserProfile']"}),
            'course': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'contributions'", 'to': u"orm['evaluation.Course']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'order': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'questionnaires': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'contributions'", 'blank': 'True', 'to': u"orm['evaluation.Questionnaire']"}),
            'responsible': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        u'evaluation.course': {
            'Meta': {'ordering': "('semester', 'degree', 'name_de')", 'unique_together': "(('semester', 'degree', 'name_de'), ('semester', 'degree', 'name_en'))", 'object_name': 'Course'},
            'degree': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'kind': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'last_modified_time': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'last_modified_user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'null': 'True', 'to': u"orm['evaluation.UserProfile']"}),
            'name_de': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'name_en': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'participant_count': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'participants': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['evaluation.UserProfile']", 'symmetrical': 'False', 'blank': 'True'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['evaluation.Semester']"}),
            'state': ('django_fsm.db.fields.fsmfield.FSMField', [], {'default': "'new'", 'max_length': '50'}),
            'vote_end_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'vote_start_date': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'voter_count': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'voters': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'+'", 'blank': 'True', 'to': u"orm['evaluation.UserProfile']"})
        },
        u'evaluation.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '1024'})
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
        u'evaluation.likertanswer': {
            'Meta': {'object_name': 'LikertAnswer'},
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
            'cc_users': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'cc_users2'", 'blank': 'True', 'to': u"orm['evaluation.UserProfile']"}),
            'delegates': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "'represented_users'", 'blank': 'True', 'to': u"orm['evaluation.UserProfile']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_external': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'login_key': ('django.db.models.fields.IntegerField', [], {'null': 'True', 'blank': 'True'}),
            'login_key_valid_until': ('django.db.models.fields.DateField', [], {'null': 'True'}),
            'picture': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '1024', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['auth.User']", 'unique': 'True'})
        }
    }

    complete_apps = ['evaluation']