# -*- coding: utf-8 -*-
 
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models
from django.db.models import get_app, get_models
 
 
class Migration(SchemaMigration):
	 
	# old_name => new_name
	apps_to_rename = {
		'fsr' : 'staff'
	}
	 
	def forwards(self, orm):
	 
		for old_appname, new_appname in self.apps_to_rename.items():
		 
			# Renaming model from 'Foo' to 'Bar'
			db.execute("UPDATE south_migrationhistory SET app_name = %s WHERE app_name = %s", [new_appname, old_appname])
			db.execute("UPDATE django_content_type SET app_label = %s WHERE app_label = %s", [new_appname, old_appname])
			app = get_app(new_appname)
			
			for model in get_models(app, include_auto_created=True):
				if model._meta.proxy == True:
					continue
				 
				new_table_name = model._meta.db_table
				old_table_name = old_appname + new_table_name[len(new_appname):]

				db.rename_table(old_table_name, new_table_name)
	 
	def backwards(self, orm):
		 
		for old_appname, new_appname in self.apps_to_rename.items():
			# Renaming model from 'Foo' to 'Bar'
			db.execute("UPDATE south_migrationhistory SET app_name = %s WHERE app_name = %s", [old_appname, new_appname])
			db.execute("UPDATE django_content_type SET app_label = %s WHERE app_label = %s", [old_appname, new_appname])
			app = get_app(new_appname)
			
			for model in get_models(app, include_auto_created=True):
				if model._meta.proxy == True:
					continue

				old_table_name = model._meta.db_table
				new_table_name = old_appname + old_table_name[len(new_appname):]

				db.rename_table(old_table_name, new_table_name)
