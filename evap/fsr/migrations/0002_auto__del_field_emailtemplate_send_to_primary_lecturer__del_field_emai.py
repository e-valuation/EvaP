# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Deleting field 'EmailTemplate.send_to_primary_lecturer'
        db.delete_column('fsr_emailtemplate', 'send_to_primary_lecturer')

        # Deleting field 'EmailTemplate.send_to_secondary_lecturer'
        db.delete_column('fsr_emailtemplate', 'send_to_secondary_lecturer')


    def backwards(self, orm):
        
        # Adding field 'EmailTemplate.send_to_primary_lecturer'
        db.add_column('fsr_emailtemplate', 'send_to_primary_lecturer', self.gf('django.db.models.fields.BooleanField')(default=False), keep_default=False)

        # Adding field 'EmailTemplate.send_to_secondary_lecturer'
        db.add_column('fsr_emailtemplate', 'send_to_secondary_lecturer', self.gf('django.db.models.fields.BooleanField')(default=False), keep_default=False)


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
