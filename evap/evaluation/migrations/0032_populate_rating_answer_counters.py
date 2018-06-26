from django.db import migrations


def populate_rating_answer_counters(apps, _schema_editor):
    LikertAnswerCounter = apps.get_model('evaluation', 'LikertAnswerCounter')
    GradeAnswerCounter = apps.get_model('evaluation', 'GradeAnswerCounter')
    RatingAnswerCounter = apps.get_model('evaluation', 'RatingAnswerCounter')

    for counter in list(LikertAnswerCounter.objects.all()) + list(GradeAnswerCounter.objects.all()):
        RatingAnswerCounter.objects.create(question=counter.question, contribution=counter.contribution, answer=counter.answer, count=counter.count)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0031_add_rating_answer_counter'),
    ]

    operations = [
        migrations.RunPython(populate_rating_answer_counters),
    ]
