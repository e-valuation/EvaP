# encoding: utf-8
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

from evap.fsr.models import EmailTemplate

class Migration(DataMigration):

    def forwards(self, orm):
        EmailTemplate.create_initial_instances()

    def backwards(self, orm):
        pass


    models = {
        'fsr.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        }
    }

    complete_apps = ['fsr']
