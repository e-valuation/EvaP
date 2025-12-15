from django.db import migrations


def migrate_single_results(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    Question = apps.get_model("evaluation", "Question")
    Questionnaire = apps.get_model("evaluation", "Questionnaire")
    RatingAnswerCounter = apps.get_model("evaluation", "RatingAnswerCounter")
    TextAnswer = apps.get_model("evaluation", "TextAnswer")

    # Don't create a questionnaire when running the migration on a database without single results
    # E.g. when running on an empty database before loading test data
    if not Evaluation.objects.filter(is_single_result=True).exists():
        return

    single_result_questionnaire = Questionnaire.objects.get(name_en="Single result")
    assert single_result_questionnaire.questions.count() == 1
    assert single_result_questionnaire.questions.first().type == 2  # GRADE question

    overall_rating_questionnaire, created = Questionnaire.objects.get_or_create(
        name_en="Total grade",
        type=30,  # BOTTOM questionnaire
        defaults={"name_de": "Gesamtnote"},
    )
    if created:
        Question.objects.create(
            questionnaire=overall_rating_questionnaire,
            type=2,  # GRADE question
            allows_additional_textanswers=False,
            text_en="Which grade would you give the course in total?",
            text_de="Wie würdest du die Veranstaltung insgesamt bewerten?",
        )
    assert overall_rating_questionnaire.questions.count() == 1
    overall_rating_question = overall_rating_questionnaire.questions.first()

    for single_result in Evaluation.objects.filter(is_single_result=True):
        assert not TextAnswer.objects.filter(contribution__evaluation=single_result).exists()
        assert single_result.contributions.count() == 1  # general contribution
        general_contribution = single_result.contributions.get(contributor=None)

        rating_answer_counters = RatingAnswerCounter.objects.filter(contribution__evaluation=single_result).all()
        for rating_answer_counter in rating_answer_counters:
            assert rating_answer_counter.question.questionnaire == single_result_questionnaire
            rating_answer_counter.question = overall_rating_question
            rating_answer_counter.save()

        general_contribution.questionnaires.remove(single_result_questionnaire)
        general_contribution.questionnaires.add(overall_rating_questionnaire)

        single_result.is_single_result = False
        single_result.save()

    single_result_questionnaire.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("evaluation", "0150_rename_degrees_to_programs"),
    ]

    operations = [migrations.RunPython(migrate_single_results, reverse_code=migrations.RunPython.noop)]
