from django.db import migrations


def add_group(apps, _schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.create(name="Grade publisher")


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_group),
    ]
