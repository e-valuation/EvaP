from django.forms.models import inlineformset_factory
from model_bakery import baker

from evap.contributor.forms import EditorContributionForm, EvaluationForm
from evap.evaluation.models import Contribution, Evaluation, Program, Questionnaire, UserProfile
from evap.evaluation.tests.tools import TestCase, WebTest, get_form_data_from_instance
from evap.staff.forms import ContributionFormset


class EvaluationFormTests(TestCase):
    def test_fields_disabled_when_editors_disallowed_to_edit(self):
        evaluation = baker.make(Evaluation)

        form = EvaluationForm(instance=evaluation)
        self.assertFalse(all(form.fields[field].disabled for field in form.fields))

        evaluation.allow_editors_to_edit = False
        evaluation.save()

        form = EvaluationForm(instance=evaluation)
        self.assertTrue(all(form.fields[field].disabled for field in form.fields))

    def test_edit_participants(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, course__programs=[baker.make(Program)], participants=[student])
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        form_data = get_form_data_from_instance(EvaluationForm, evaluation)
        form = EvaluationForm(form_data, instance=evaluation)
        self.assertEqual(len(form["participants"].initial), 1)

        form_data["participants"].remove(student.pk)
        EvaluationForm(form_data, instance=evaluation).save()
        self.assertEqual(evaluation.num_participants, 0)

        form_data["participants"].append(student.pk)
        EvaluationForm(form_data, instance=evaluation).save()
        del evaluation.num_participants  # discard cached property
        self.assertEqual(evaluation.num_participants, 1)


class ContributionFormsetTests(TestCase):
    def test_managers_only(self):
        """
        Asserts that managers_only questionnaires are shown to Editors only if they are already selected for a
        contribution of the Evaluation.
        Regression test for #593.
        """
        evaluation = baker.make(Evaluation)
        questionnaire = baker.make(
            Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.EDITORS
        )
        questionnaire_managers_only = baker.make(
            Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.MANAGERS
        )
        # one hidden questionnaire that should never be shown
        baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.HIDDEN)

        # just the normal questionnaire should be shown.
        contribution1 = baker.make(
            Contribution, evaluation=evaluation, contributor=baker.make(UserProfile), questionnaires=[]
        )

        InlineContributionFormset = inlineformset_factory(
            Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=1
        )
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={"evaluation": evaluation})

        expected = {questionnaire}
        self.assertEqual(expected, set(formset.forms[0].fields["questionnaires"].queryset))
        self.assertEqual(expected, set(formset.forms[1].fields["questionnaires"].queryset))

        # now a manager adds a manager only questionnaire, which should be shown as well
        contribution1.questionnaires.set([questionnaire_managers_only])

        InlineContributionFormset = inlineformset_factory(
            Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=1
        )
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={"evaluation": evaluation})

        expected = {questionnaire, questionnaire_managers_only}
        self.assertEqual(expected, set(formset.forms[0].fields["questionnaires"].queryset))
        self.assertEqual(expected, set(formset.forms[1].fields["questionnaires"].queryset))

    def test_locked_questionnaire(self):
        """
        Asserts that locked (general) questionnaires cannot be changed.
        """
        questionnaire = baker.make(
            Questionnaire, type=Questionnaire.Type.TOP, is_locked=False, visibility=Questionnaire.Visibility.EDITORS
        )
        locked_questionnaire = baker.make(
            Questionnaire, type=Questionnaire.Type.TOP, is_locked=True, visibility=Questionnaire.Visibility.EDITORS
        )

        evaluation = baker.make(Evaluation)
        evaluation.general_contribution.questionnaires.add(questionnaire)

        form_data = get_form_data_from_instance(EvaluationForm, evaluation)
        form_data["general_questionnaires"] = [questionnaire.pk, locked_questionnaire.pk]  # add locked questionnaire

        form = EvaluationForm(form_data, instance=evaluation)

        # Assert form is valid, but locked questionnaire is not added
        form.save()
        self.assertEqual({questionnaire}, set(evaluation.general_contribution.questionnaires.all()))

        evaluation.general_contribution.questionnaires.add(locked_questionnaire)

        form_data = get_form_data_from_instance(EvaluationForm, evaluation)
        form_data["general_questionnaires"] = [questionnaire.pk]  # remove locked questionnaire

        form = EvaluationForm(form_data, instance=evaluation)

        # Assert form is valid, but locked questionnaire is not removed
        form.save()
        self.assertEqual(
            {questionnaire, locked_questionnaire}, set(evaluation.general_contribution.questionnaires.all())
        )

    def test_existing_contributors_are_in_queryset(self):
        """
        Asserts that users that should normally not be in the contributor queryset are in it when they are already set.
        Regression test for #1414.
        """
        evaluation = baker.make(Evaluation)
        non_proxy_user = baker.make(UserProfile)
        proxy_user = baker.make(UserProfile, is_proxy_user=True)
        contribution1 = baker.make(Contribution, evaluation=evaluation, contributor=non_proxy_user, questionnaires=[])

        InlineContributionFormset = inlineformset_factory(
            Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=1
        )
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={"evaluation": evaluation})

        self.assertEqual({non_proxy_user}, set(formset.forms[0].fields["contributor"].queryset))

        # now a manager adds the proxy user as a contributor.
        contribution1.contributor = proxy_user
        contribution1.save()

        InlineContributionFormset = inlineformset_factory(
            Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=1
        )
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={"evaluation": evaluation})

        self.assertEqual({proxy_user, non_proxy_user}, set(formset.forms[0].fields["contributor"].queryset))


class ContributionFormsetWebTests(WebTest):
    csrf_checks = False

    def test_form_ordering(self):
        """
        Asserts that the contribution formset is correctly sorted,
        and that an ordering changed by the user survives the reload
        when the user submits the form with errors.
        Regression test for #456.
        """
        evaluation = baker.make(Evaluation, state=Evaluation.State.PREPARED)
        user1 = baker.make(UserProfile, email="user1@institution.example.com")
        user2 = baker.make(UserProfile, email="user2@institution.example.com")
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        contribution1 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=user1,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            questionnaires=[questionnaire],
            order=1,
        )
        contribution2 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=user2,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            questionnaires=[questionnaire],
            order=2,
        )

        # almost everything is missing in this set of data,
        # so we're guaranteed to have some errors
        data = {
            "contributions-TOTAL_FORMS": 2,
            "contributions-INITIAL_FORMS": 2,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-id": contribution1.id,
            "contributions-1-id": contribution2.id,
            "operation": "save",
        }

        data["contributions-0-order"] = 1
        data["contributions-1-order"] = 2
        response = str(self.app.post(f"/contributor/evaluation/{evaluation.pk}/edit", params=data, user=user1))
        self.assertTrue(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))

        data["contributions-0-order"] = 2
        data["contributions-1-order"] = 1
        response = str(self.app.post(f"/contributor/evaluation/{evaluation.pk}/edit", params=data, user=user1))
        self.assertFalse(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))
