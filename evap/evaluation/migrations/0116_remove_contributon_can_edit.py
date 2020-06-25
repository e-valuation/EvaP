from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0115_add_contribution_role'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contribution',
            name='can_edit',
        ),
    ]
