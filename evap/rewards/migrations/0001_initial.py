# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'RewardPointRedemptionEvent'
        db.create_table(u'rewards_rewardpointredemptionevent', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=1024)),
            ('date', self.gf('django.db.models.fields.DateField')()),
            ('redeem_end_date', self.gf('django.db.models.fields.DateField')()),
        ))
        db.send_create_signal(u'rewards', ['RewardPointRedemptionEvent'])

        # Adding model 'RewardPointGranting'
        db.create_table(u'rewards_rewardpointgranting', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user_profile', self.gf('django.db.models.fields.related.ForeignKey')(related_name='reward_point_grantings', to=orm['evaluation.UserProfile'])),
            ('semester', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='reward_point_grantings', null=True, to=orm['evaluation.Semester'])),
            ('granting_time', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('value', self.gf('django.db.models.fields.IntegerField')(default=0)),
        ))
        db.send_create_signal(u'rewards', ['RewardPointGranting'])

        # Adding model 'RewardPointRedemption'
        db.create_table(u'rewards_rewardpointredemption', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user_profile', self.gf('django.db.models.fields.related.ForeignKey')(related_name='reward_point_redemptions', to=orm['evaluation.UserProfile'])),
            ('redemption_time', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('value', self.gf('django.db.models.fields.IntegerField')(default=0)),
            ('event', self.gf('django.db.models.fields.related.ForeignKey')(related_name='reward_point_redemptions', to=orm['rewards.RewardPointRedemptionEvent'])),
        ))
        db.send_create_signal(u'rewards', ['RewardPointRedemption'])


    def backwards(self, orm):
        # Deleting model 'RewardPointRedemptionEvent'
        db.delete_table(u'rewards_rewardpointredemptionevent')

        # Deleting model 'RewardPointGranting'
        db.delete_table(u'rewards_rewardpointgranting')

        # Deleting model 'RewardPointRedemption'
        db.delete_table(u'rewards_rewardpointredemption')


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
        u'evaluation.semester': {
            'Meta': {'ordering': "('-created_at', 'name_de')", 'object_name': 'Semester'},
            'created_at': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name_de': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'name_en': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'})
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
        },
        u'rewards.rewardpointgranting': {
            'Meta': {'object_name': 'RewardPointGranting'},
            'granting_time': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'semester': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'reward_point_grantings'", 'null': 'True', 'to': u"orm['evaluation.Semester']"}),
            'user_profile': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'reward_point_grantings'", 'to': u"orm['evaluation.UserProfile']"}),
            'value': ('django.db.models.fields.IntegerField', [], {'default': '0'})
        },
        u'rewards.rewardpointredemption': {
            'Meta': {'object_name': 'RewardPointRedemption'},
            'event': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'reward_point_redemptions'", 'to': u"orm['rewards.RewardPointRedemptionEvent']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'redemption_time': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'user_profile': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'reward_point_redemptions'", 'to': u"orm['evaluation.UserProfile']"}),
            'value': ('django.db.models.fields.IntegerField', [], {'default': '0'})
        },
        u'rewards.rewardpointredemptionevent': {
            'Meta': {'object_name': 'RewardPointRedemptionEvent'},
            'date': ('django.db.models.fields.DateField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '1024'}),
            'redeem_end_date': ('django.db.models.fields.DateField', [], {})
        }
    }

    complete_apps = ['rewards']