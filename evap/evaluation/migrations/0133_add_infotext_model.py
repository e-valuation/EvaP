from django.db import migrations, models
from evap.evaluation.models import NotHalfEmptyConstraint


def create_infotexts(apps, _schema_editor):
    infotext = apps.get_model("evaluation", "Infotext")

    for page in ["student_index", "contributor_index", "grades_pages"]:
        infotext.objects.create(title_en="", title_de="", content_en="", content_de="", page=page)


class Migration(migrations.Migration):
    dependencies = [
        ('evaluation', '0132_textanswer_is_flagged'),
    ]

    operations = [
        migrations.CreateModel(
            name='Infotext',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title_de', models.CharField(max_length=255, blank=True, verbose_name='title (german)')),
                ('title_en', models.CharField(max_length=255, blank=True, verbose_name='title (english)')),
                ('content_de', models.TextField(blank=True, verbose_name='content (german)')),
                ('content_en', models.TextField(blank=True, verbose_name='content (english)')),
                ('page', models.CharField(
                    choices=[('student_index', 'Student index page'), ('contributor_index', 'Contributor index page'),
                             ('grades_pages', 'Grade publishing pages')], max_length=30, unique=True, null=False,
                    blank=False, verbose_name='page for the infotext to be visible on')),
            ],
            options={
                'verbose_name': 'infotext',
                'verbose_name_plural': 'infotexts',
            },
        ),
        migrations.AddConstraint(
            model_name="infotext",
            constraint=NotHalfEmptyConstraint(
                fields=["title_de", "title_en", "content_de", "content_en"],
                name="infotext_not_half_empty",
            ),
        ),
        migrations.RunPython(create_infotexts, reverse_code=migrations.RunPython.noop)
    ]
