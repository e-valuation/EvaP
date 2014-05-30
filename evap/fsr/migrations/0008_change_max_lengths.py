# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):

        # Changing field 'EmailTemplate.name'
        db.alter_column(u'fsr_emailtemplate', 'name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=1024))

        # Changing field 'EmailTemplate.subject'
        db.alter_column(u'fsr_emailtemplate', 'subject', self.gf('django.db.models.fields.CharField')(max_length=1024))

    def backwards(self, orm):

        # Changing field 'EmailTemplate.name'
        db.alter_column(u'fsr_emailtemplate', 'name', self.gf('django.db.models.fields.CharField')(max_length=100, unique=True))

        # Changing field 'EmailTemplate.subject'
        db.alter_column(u'fsr_emailtemplate', 'subject', self.gf('django.db.models.fields.CharField')(max_length=100))

    models = {
        u'fsr.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '1024'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '1024'})
        }
    }

    complete_apps = ['fsr']