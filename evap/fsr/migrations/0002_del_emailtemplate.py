# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):
    depends_on = (
        ('evaluation', '0004_add_emailtemplate'),
    )
    def forwards(self, orm):
        pass
    def backwards(self, orm):
        pass

        
    models = {
        
    }

    complete_apps = ['fsr']