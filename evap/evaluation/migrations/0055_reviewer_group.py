from django.contrib.auth.models import Group
from django.db import migrations


def add_group(_apps, _schema_editor):
    Group.objects.create(name="Reviewer")


def delete_group(_apps, _schema_editor):
    Group.objects.get(name="Reviewer").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0054_userprofile_language'),
    ]

    operations = [
        migrations.RunPython(add_group, reverse_code=delete_group),
    ]
