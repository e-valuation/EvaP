from django.db import migrations


def create_answer_counters(apps, _schema_editor):
    GradeAnswer = apps.get_model('evaluation', 'GradeAnswer')
    LikertAnswer = apps.get_model('evaluation', 'LikertAnswer')
    GradeAnswerCounter = apps.get_model('evaluation', 'GradeAnswerCounter')
    LikertAnswerCounter = apps.get_model('evaluation', 'LikertAnswerCounter')

    for grade_answer in GradeAnswer.objects.all():
        grade_answer_counter, __ = GradeAnswerCounter.objects.get_or_create(question=grade_answer.question, contribution=grade_answer.contribution, answer=grade_answer.answer)
        grade_answer_counter.count += 1
        grade_answer_counter.save()

    for likert_answer in LikertAnswer.objects.all():
        likert_answer_counter, __ = LikertAnswerCounter.objects.get_or_create(question=likert_answer.question, contribution=likert_answer.contribution, answer=likert_answer.answer)
        likert_answer_counter.count += 1
        likert_answer_counter.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0022_gradeanswercounter_likertanswercounter'),
    ]

    operations = [
        migrations.RunPython(create_answer_counters),
    ]
