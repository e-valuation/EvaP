from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0004_rename_preliminary_to_midterm'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gradedocument',
            unique_together=set([('course', 'description')]),
        ),
    ]
