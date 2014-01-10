# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

class Migration(DataMigration):

    def forwards(self, orm):
        for template in orm.EmailTemplate.objects.filter(name="Logon Key Created").all():
            template.name = "Login Key Created"
            template.save()

    def backwards(self, orm):
        for template in orm.EmailTemplate.objects.filter(name="Login Key Created").all():
            template.name = "Logon Key Created"
            template.save()

    models = {
        u'fsr.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        }
    }

    complete_apps = ['fsr']
    symmetrical = True
