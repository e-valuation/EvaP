# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

from evap.fsr.models import EmailTemplate

class Migration(SchemaMigration):

    def forwards(self, orm):
        EmailTemplate(pk=3, name="Template for publishing", subject="[EvaP] A course has been published", body="").save()


    def backwards(self, orm):
        try:
            EmailTemplate.objects.get(pk=3).delete()
        except EmailTemplate.DoesNotExist:
            pass


    models = {
        'fsr.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'use': ('django.db.models.fields.BooleanField', [], {'default': 'True'})
        }
    }

    complete_apps = ['fsr']
