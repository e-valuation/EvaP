from django.db import migrations, models
from evap.evaluation.models import Infotext


def create_infotexts(apps, _schema_editor):
    infotext = apps.get_model("evaluation", "Infotext")

    for page in Infotext.Page:
        infotext.objects.create(title_en="", title_de="", content_en="", content_de="", page=page)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0131_userprofile_ordering'),
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
                ('page', models.CharField(choices=[('student_index', 'Student index page'), ('contributor_index', 'Contributor index page'), ('grades_pages', 'Grade publishing pages')], max_length=30, unique=True, null=False, blank=False, verbose_name='page for the infotext to be visible on')),
            ],
            options={
                'verbose_name': 'infotext',
                'verbose_name_plural': 'infotexts',
            },
        ),
        migrations.AddConstraint(
            model_name="infotext",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("content_de", ""), ("content_en", ""), ("title_de", ""), ("title_en", "")),
                    models.Q(
                        models.Q(
                            ("content_de", ""), ("content_en", ""), ("title_de", ""), ("title_en", ""), _connector="OR"
                        ),
                        _negated=True,
                    ),
                    _connector="OR",
                ),
                name="infotexts_not_half_empty",
                violation_error_message="Please supply either all or no fields for this infotext.",
            ),
        ),
        migrations.RunPython(create_infotexts, reverse_code=lambda a, b: None)
    ]
