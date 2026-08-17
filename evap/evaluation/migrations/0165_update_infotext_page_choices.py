from django.db import migrations, models


def create_infotext(apps, _schema_editor):
    infotext = apps.get_model("evaluation", "Infotext")
    infotext.objects.create(title_en="", title_de="", content_en="", content_de="", page="rewards_index")


def remove_infotext(apps, _schema_editor):
    infotext = apps.get_model("evaluation", "Infotext")
    infotext.objects.get(page="rewards_index").delete()


class Migration(migrations.Migration):
    dependencies = [
        (
            "evaluation",
            "0164_remove_questionnaire_questionnaire_visibility_choices_and_more",
        ),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="infotext",
            name="Infotext_page_choices",
        ),
        migrations.AlterField(
            model_name="infotext",
            name="page",
            field=models.CharField(
                choices=[
                    ("student_index", "Student index page"),
                    ("contributor_index", "Contributor index page"),
                    ("grades_pages", "Grade publishing pages"),
                    ("rewards_index", "Rewards index page"),
                ],
                max_length=30,
                unique=True,
                verbose_name="page for the infotext to be visible on",
            ),
        ),
        migrations.AddConstraint(
            model_name="infotext",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "page__in",
                        [
                            "student_index",
                            "contributor_index",
                            "grades_pages",
                            "rewards_index",
                        ],
                    )
                ),
                name="Infotext_page_choices",
            ),
        ),
        migrations.RunPython(create_infotext, reverse_code=remove_infotext),
    ]
