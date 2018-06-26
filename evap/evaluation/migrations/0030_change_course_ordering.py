from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0029_user_sorting_and_related_names_to_contribution'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='course',
            options={'ordering': ('name_de',), 'verbose_name_plural': 'courses', 'verbose_name': 'course'},
        ),
    ]
