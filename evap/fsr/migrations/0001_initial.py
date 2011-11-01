# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

from evap.fsr.models import EmailTemplate

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'EmailTemplate'
        db.create_table('fsr_emailtemplate', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('use', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('send_to_primary_lecturer', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('send_to_secondary_lecturer', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('subject', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('body', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal('fsr', ['EmailTemplate'])
        
        EmailTemplate.create_initial_instances()

    def backwards(self, orm):
        
        # Deleting model 'EmailTemplate'
        db.delete_table('fsr_emailtemplate')


    models = {
        'fsr.emailtemplate': {
            'Meta': {'object_name': 'EmailTemplate'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'send_to_primary_lecturer': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'send_to_secondary_lecturer': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'subject': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'use': ('django.db.models.fields.BooleanField', [], {'default': 'True'})
        }
    }

    complete_apps = ['fsr']
