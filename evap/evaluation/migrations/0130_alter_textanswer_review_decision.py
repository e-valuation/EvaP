from django.db import migrations, models


def forward(apps, _schema_editor):
    TextAnswer = apps.get_model("evaluation", "TextAnswer")
    TextAnswer.objects.filter(review_decision="HI").update(review_decision="DE")
    TextAnswer.objects.filter(review_decision="NR").update(review_decision="UN")


def backward(apps, _schema_editor):
    TextAnswer = apps.get_model("evaluation", "TextAnswer")
    TextAnswer.objects.filter(review_decision="DE").update(review_decision="HI")
    TextAnswer.objects.filter(review_decision="UN").update(review_decision="NR")


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0129_rename_state_textanswer_review_decision"),
    ]

    operations = [
        migrations.AlterField(
            model_name="textanswer",
            name="review_decision",
            field=models.CharField(
                choices=[("PU", "public"), ("PR", "private"), ("DE", "deleted"), ("UN", "undecided")],
                default="UN",
                max_length=2,
                verbose_name="review decision for the answer",
            ),
        ),
        migrations.RunPython(forward, reverse_code=backward),
    ]
