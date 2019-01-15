from django.db import migrations


def add_group(apps, _schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.create(name="Reviewer", pk=2)


def delete_group(apps, _schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get(name="Reviewer").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0054_userprofile_language'),
    ]

    operations = [
        migrations.RunPython(add_group, reverse_code=delete_group),
    ]
