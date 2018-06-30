from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0016_apply_course_degrees'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='course',
            options={'verbose_name': 'course', 'ordering': ('semester', 'name_de'), 'verbose_name_plural': 'courses'},
        ),
        migrations.AlterUniqueTogether(
            name='course',
            unique_together=set([('semester', 'name_en'), ('semester', 'name_de')]),
        ),
        migrations.RemoveField(
            model_name='course',
            name='degree',
        ),
    ]
