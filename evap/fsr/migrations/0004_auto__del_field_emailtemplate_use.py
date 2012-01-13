# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Deleting field 'EmailTemplate.use'
        db.delete_column('fsr_emailtemplate', 'use')


    def backwards(self, orm):
        
        # Adding field 'EmailTemplate.use'
        db.add_column('fsr_emailtemplate', 'use', self.gf('django.db.models.fields.BooleanField')(default=True), keep_default=False)


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
