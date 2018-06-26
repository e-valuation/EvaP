from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0017_delete_old_degrees'),
    ]

    operations = [
        migrations.AlterField(
            model_name='degree',
            name='name_de',
            field=models.CharField(unique=True, verbose_name='name (german)', max_length=1024),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='degree',
            name='name_en',
            field=models.CharField(unique=True, verbose_name='name (english)', max_length=1024),
            preserve_default=True,
        ),
    ]
