from unittest.mock import patch
from django.forms.models import inlineformset_factory
from django.test import TestCase
from model_bakery import baker

from evap.evaluation.models import (Contribution, Course, Degree, EmailTemplate, Evaluation, Question,
                                    Questionnaire, Semester, UserProfile)
from evap.evaluation.tests.tools import (create_evaluation_with_responsible_and_editor, get_form_data_from_instance,
                                         to_querydict)
from evap.staff.forms import (ContributionForm, ContributionFormSet, CourseForm, EvaluationEmailForm, EvaluationForm,
                              QuestionnaireForm, SingleResultForm, UserForm)
from evap.contributor.forms import EvaluationForm as ContributorEvaluationForm


class QuestionnaireFormTest(TestCase):
    def test_force_highest_order(self):
        baker.make(Questionnaire, order=45, type=Questionnaire.Type.TOP)

        question = baker.make(Question)

        data = {
            'description_de': 'English description',
            'description_en': 'German description',
            'name_de': 'A name',
            'name_en': 'A german name',
            'public_name_en': 'A display name',
            'public_name_de': 'A german display name',
            'questions-0-id': question.id,
            'order': 0,
            'type': Questionnaire.Type.TOP,
            'visibility': 2,
        }

        form = QuestionnaireForm(data=data)
        self.assertTrue(form.is_valid())
        questionnaire = form.save(force_highest_order=True)
        self.assertEqual(questionnaire.order, 46)

    def test_automatic_order_correction_on_type_change(self):
        baker.make(Questionnaire, order=72, type=Questionnaire.Type.BOTTOM)

        questionnaire = baker.make(Questionnaire, order=7, type=Questionnaire.Type.TOP)
        question = baker.make(Question)

        data = {
            'description_de': questionnaire.description_de,
            'description_en': questionnaire.description_en,
            'name_de': questionnaire.name_de,
            'name_en': questionnaire.name_en,
            'public_name_en': questionnaire.public_name_en,
            'public_name_de': questionnaire.public_name_de,
            'questions-0-id': question.id,
            'order': questionnaire.order,
            'type': Questionnaire.Type.BOTTOM,
            'visibility': 2,
        }

        form = QuestionnaireForm(instance=questionnaire, data=data)
        self.assertTrue(form.is_valid())
        questionnaire = form.save()
        self.assertEqual(questionnaire.order, 73)


class EvaluationEmailFormTests(TestCase):
    def test_evaluation_email_form(self):
        """
            Tests the EvaluationEmailForm with one valid and one invalid input dataset.
        """
        evaluation = create_evaluation_with_responsible_and_editor()
        data = {"body": "wat", "subject": "some subject", "recipients": [EmailTemplate.Recipients.DUE_PARTICIPANTS]}
        form = EvaluationEmailForm(evaluation=evaluation, data=data)
        self.assertTrue(form.is_valid())
        form.send(None)

        data = {"body": "wat", "subject": "some subject"}
        form = EvaluationEmailForm(evaluation=evaluation, data=data)
        self.assertFalse(form.is_valid())


class UserFormTests(TestCase):
    def test_user_form(self):
        """
            Tests the UserForm with one valid and one invalid input dataset.
        """
        user = baker.make(UserProfile)
        another_user = baker.make(UserProfile)
        data = {"username": "mklqoep50x2", "email": "a@b.ce"}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

        data = {"username": another_user.username, "email": "a@b.c"}
        form = UserForm(instance=user, data=data)
        self.assertFalse(form.is_valid())

    def test_user_with_same_email(self):
        """
            Tests whether the user form correctly handles email adresses
            that already exist in the database
            Regression test for #590
        """
        user = baker.make(UserProfile, email="uiae@example.com")

        data = {"username": "uiae", "email": user.email}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

    def test_user_with_same_username(self):
        """
            Tests whether the user form correctly handles usernames
            that already exist in the database
        """
        user = baker.make(UserProfile)

        data = {"username": user.username}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

    def test_user_cannot_be_removed_from_evaluation_already_voted_for(self):
        student = baker.make(UserProfile)
        baker.make(Evaluation, participants=[student], voters=[student])

        form_data = get_form_data_from_instance(UserForm, student)
        form_data["evaluations_participating_in"] = []
        form = UserForm(form_data, instance=student)

        self.assertFalse(form.is_valid())
        self.assertIn('evaluations_participating_in', form.errors)
        self.assertIn("Evaluations for which the user already voted can't be removed", form.errors['evaluations_participating_in'][0])


class SingleResultFormTests(TestCase):
    def test_single_result_form_saves_participant_and_voter_count(self):
        course = baker.make(Course)
        evaluation = Evaluation(course=course, is_single_result=True)
        form_data = {
            "name_de": "qwertz",
            "name_en": "qwertz",
            "weight": 1,
            "event_date": "2014-01-01",
            "answer_1": 6,
            "answer_2": 0,
            "answer_3": 2,
            "answer_4": 0,
            "answer_5": 2,
            "course": course.pk
        }
        form = SingleResultForm(form_data, instance=evaluation, semester=evaluation.course.semester)
        self.assertTrue(form.is_valid())

        form.save(user=baker.make(UserProfile))

        evaluation = Evaluation.objects.get()
        self.assertEqual(evaluation.num_participants, 10)
        self.assertEqual(evaluation.num_voters, 10)


class ContributionFormsetTests(TestCase):
    def test_contribution_form_set(self):
        """
            Tests the ContributionFormset with various input data sets.
        """
        evaluation = baker.make(Evaluation)
        user1 = baker.make(UserProfile)
        user2 = baker.make(UserProfile)
        baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

        ContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-evaluation': evaluation.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-0-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        })
        # no contributor
        self.assertFalse(ContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data.copy()).is_valid())
        # valid
        data['contributions-0-contributor'] = user1.pk
        self.assertTrue(ContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data.copy()).is_valid())
        # duplicate contributor
        data['contributions-TOTAL_FORMS'] = 2
        data['contributions-1-contributor'] = user1.pk
        data['contributions-1-evaluation'] = evaluation.pk
        data['contributions-1-questionnaires'] = questionnaire.pk
        data['contributions-1-order'] = 1
        data['contributions-1-textanswer_visibility'] = Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS
        self.assertFalse(ContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data).is_valid())
        # two contributors
        data['contributions-1-contributor'] = user2.pk
        data['contributions-1-responsibility'] = Contribution.Responsibility.IS_EDITOR
        self.assertTrue(ContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data).is_valid())

    def test_dont_validate_deleted_contributions(self):
        """
            Tests whether contributions marked for deletion are validated.
            Regression test for #415 and #244
        """
        evaluation = baker.make(Evaluation)
        user1 = baker.make(UserProfile)
        user2 = baker.make(UserProfile)
        baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

        contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        # Here we have two editors (one of them deleted with no questionnaires), and a deleted contributor with no questionnaires.

        data = to_querydict({
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-evaluation': evaluation.pk,
            'contributions-0-questionnaires': "",
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-0-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-0-contributor': user1.pk,
            'contributions-1-evaluation': evaluation.pk,
            'contributions-1-questionnaires': questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-1-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-1-contributor': user2.pk,
            'contributions-2-evaluation': evaluation.pk,
            'contributions-2-questionnaires': "",
            'contributions-2-order': 1,
            'contributions-2-responsibility': "CONTRIBUTOR",
            'contributions-2-textanswer_visibility': Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
            'contributions-2-contributor': user2.pk,
        })

        # Without deletion, this form should be invalid
        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        self.assertFalse(formset.is_valid())

        data['contributions-0-DELETE'] = 'on'
        data['contributions-2-DELETE'] = 'on'

        # With deletion, it should be valid
        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        self.assertTrue(formset.is_valid())

    @staticmethod
    def test_deleted_empty_contribution_does_not_crash():
        """
            When removing the empty extra contribution formset, validating the form should not crash.
            Similarly, when removing the contribution formset of an existing contributor, and entering some data in the extra formset, it should not crash.
            Regression test for #1057
        """
        evaluation = baker.make(Evaluation)
        user1 = baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

        contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-evaluation': evaluation.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-0-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-0-contributor': user1.pk,
            'contributions-1-evaluation': evaluation.pk,
            'contributions-1-questionnaires': "",
            'contributions-1-order': -1,
            'contributions-1-responsibility': "CONTRIBUTOR",
            'contributions-1-textanswer_visibility': Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
            'contributions-1-contributor': "",
        })

        # delete extra formset
        data['contributions-1-DELETE'] = 'on'
        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        formset.is_valid()
        data['contributions-1-DELETE'] = ''

        # delete first, change data in extra formset
        data['contributions-0-DELETE'] = 'on'
        data['contributions-1-responsibility'] = Contribution.Responsibility.IS_EDITOR
        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        formset.is_valid()

    def test_take_deleted_contributions_into_account(self):
        """
            Tests whether contributions marked for deletion are properly taken into account
            when the same contributor got added again in the same formset.
            Regression test for #415
        """
        evaluation = baker.make(Evaluation)
        user1 = baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        contribution1 = baker.make(Contribution, evaluation=evaluation, contributor=user1, can_edit=True,
                                   textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS, questionnaires=[questionnaire])

        contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-evaluation': evaluation.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-0-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-evaluation': evaluation.pk,
            'contributions-1-questionnaires': questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-id': '',
            'contributions-1-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-1-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-1-contributor': user1.pk,
        })

        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        self.assertTrue(formset.is_valid())

    def test_there_can_be_no_contributions(self):
        """
            Tests that there can also be no contribution
            Regression test for #1347
        """
        evaluation = baker.make(Evaluation)
        contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 0,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
        })

        formset = contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation}, data=data)
        self.assertTrue(formset.is_valid())

    def test_hidden_and_managers_only(self):
        """
            Asserts that hidden questionnaires are shown to managers only if they are already selected for a
            contribution of the Evaluation, and that manager only questionnaires are always shown.
            Regression test for #593.
        """
        evaluation = baker.make(Evaluation)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.EDITORS)
        questionnaire_hidden = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.HIDDEN)
        questionnaire_managers_only = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR, visibility=Questionnaire.Visibility.MANAGERS)

        # The normal and managers_only questionnaire should be shown.
        contribution1 = baker.make(Contribution, evaluation=evaluation, contributor=baker.make(UserProfile), questionnaires=[])

        inline_contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation})

        expected = {questionnaire, questionnaire_managers_only}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset))

        # Suppose we had a hidden questionnaire already selected, that should be shown as well.
        contribution1.questionnaires.set([questionnaire_hidden])

        inline_contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=evaluation, form_kwargs={'evaluation': evaluation})

        expected = {questionnaire, questionnaire_managers_only, questionnaire_hidden}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset))

    def test_staff_can_select_proxy_user(self):
        proxy_user = baker.make(UserProfile, is_proxy_user=True)
        course = baker.make(Course, semester=baker.make(Semester))
        form = CourseForm(instance=course)
        self.assertIn(proxy_user, form.fields['responsibles'].queryset)


class ContributionFormset775RegressionTests(TestCase):
    """
        Various regression tests for #775
    """
    @classmethod
    def setUpTestData(cls):
        cls.evaluation = baker.make(Evaluation, name_en="some evaluation")
        cls.user1 = baker.make(UserProfile)
        cls.user2 = baker.make(UserProfile)
        baker.make(UserProfile)
        cls.questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.contribution1 = baker.make(Contribution, contributor=cls.user1, evaluation=cls.evaluation, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        cls.contribution2 = baker.make(Contribution, contributor=cls.user2, evaluation=cls.evaluation)

        cls.contribution_formset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

    def setUp(self):
        self.data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 2,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': str(self.contribution1.pk),  # browsers send strings so we should too
            'contributions-0-evaluation': self.evaluation.pk,
            'contributions-0-questionnaires': self.questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.Responsibility.IS_EDITOR,
            'contributions-0-textanswer_visibility': Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            'contributions-0-contributor': self.user1.pk,
            'contributions-1-id': str(self.contribution2.pk),
            'contributions-1-evaluation': self.evaluation.pk,
            'contributions-1-questionnaires': self.questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-responsibility': "CONTRIBUTOR",
            'contributions-1-textanswer_visibility': Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
            'contributions-1-contributor': self.user2.pk,
        })

    def test_swap_contributors(self):
        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        self.assertTrue(formset.is_valid())

        # swap contributors, should still be valid
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk
        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        self.assertTrue(formset.is_valid())

    def test_move_and_delete(self):
        # move contributor2 to the first contribution and delete the second one
        # after saving, only one contribution should exist and have the contributor2
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user2.pk
        self.data['contributions-1-DELETE'] = 'on'
        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        self.assertTrue(formset.is_valid())
        formset.save()
        self.assertTrue(Contribution.objects.filter(contributor=self.user2, evaluation=self.evaluation).exists())
        self.assertFalse(Contribution.objects.filter(contributor=self.user1, evaluation=self.evaluation).exists())

    def test_extra_form(self):
        # make sure nothing crashes when an extra form is present.
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk
        self.data['contributions-TOTAL_FORMS'] = 3
        self.data['contributions-2-id'] = ""
        self.data['contributions-2-order'] = -1
        self.data['contributions-2-responsibility'] = "CONTRIBUTOR"
        self.data['contributions-2-textanswer_visibility'] = Contribution.TextAnswerVisibility.OWN_TEXTANSWERS
        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        self.assertTrue(formset.is_valid())

    def test_swap_contributors_with_extra_form(self):
        # moving a contributor to an extra form should work.
        # first, the second contributor is deleted and removed from self.data
        Contribution.objects.get(id=self.contribution2.id).delete()
        self.data['contributions-TOTAL_FORMS'] = 2
        self.data['contributions-INITIAL_FORMS'] = 1
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk
        self.data['contributions-1-id'] = ""
        self.data['contributions-1-order'] = -1
        self.data['contributions-1-responsibility'] = "CONTRIBUTOR"
        self.data['contributions-1-textanswer_visibility'] = Contribution.TextAnswerVisibility.OWN_TEXTANSWERS

        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        self.assertTrue(formset.is_valid())

    def test_handle_multivaluedicts(self):
        # make sure the workaround is not eating questionnaires
        # first, swap contributors to trigger the workaround
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk

        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        self.data.appendlist('contributions-0-questionnaires', questionnaire.pk)
        formset = self.contribution_formset(instance=self.evaluation, form_kwargs={'evaluation': self.evaluation}, data=self.data)
        formset.save()
        self.assertEqual(Questionnaire.objects.filter(contributions=self.contribution2).count(), 2)


class CourseFormTests(TestCase):
    def test_course_form_same_name(self):
        """
            Test whether giving a course the same name as another course
            in the same semester in the course edit form is invalid.
        """
        courses = baker.make(Course, semester=baker.make(Semester), responsibles=[baker.make(UserProfile)], degrees=[baker.make(Degree)], _quantity=2)

        form_data = get_form_data_from_instance(CourseForm, courses[0])
        form = CourseForm(form_data, instance=courses[0])
        self.assertTrue(form.is_valid())
        form_data['name_de'] = courses[1].name_de
        form = CourseForm(form_data, instance=courses[0])
        self.assertFalse(form.is_valid())

    def test_uniqueness_constraint_error_shown(self):
        """
            Tests whether errors being caused by a uniqueness constraint are shown in the form
        """
        courses = baker.make(Course, semester=baker.make(Semester), responsibles=[baker.make(UserProfile)], degrees=[baker.make(Degree)], _quantity=2)

        form_data = get_form_data_from_instance(CourseForm, courses[1])
        form_data["name_de"] = courses[0].name_de
        form = CourseForm(form_data, instance=courses[1])

        self.assertFalse(form.is_valid())
        self.assertIn('name_de', form.errors)
        self.assertEqual(form.errors['name_de'], ['Course with this Semester and Name (german) already exists.'])

    def test_that_proxy_user_can_be_responsible(self):
        course = baker.make(Course, semester=baker.make(Semester), degrees=[baker.make(Degree)])
        proxy = baker.make(UserProfile, is_proxy_user=True, is_active=True)
        form = CourseForm(instance=course)
        self.assertIn(proxy, form.fields['responsibles'].queryset)


class EvaluationFormTests(TestCase):
    def test_evaluation_form_same_name(self):
        """
            Test whether giving an evaluation the same name as another evaluation
            in the same course in the evaluation edit form is invalid.
        """
        course = baker.make(Course, degrees=[baker.make(Degree)])
        evaluation1 = baker.make(Evaluation, course=course, name_de="Evaluierung 1", name_en="Evaluation 1")
        evaluation2 = baker.make(Evaluation, course=course, name_de="Evaluierung 2", name_en="Evaluation 2")
        evaluation1.general_contribution.questionnaires.set([baker.make(Questionnaire)])
        evaluation2.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        form_data = get_form_data_from_instance(EvaluationForm, evaluation1)
        form_data["vote_start_datetime"] = "2098-01-01"  # needed to fix the form
        form_data["vote_end_date"] = "2099-01-01"  # needed to fix the form

        form = EvaluationForm(form_data, instance=evaluation1, semester=evaluation1.course.semester)
        self.assertTrue(form.is_valid())
        form_data['name_de'] = evaluation2.name_de
        form = EvaluationForm(form_data, instance=evaluation1, semester=evaluation1.course.semester)
        self.assertFalse(form.is_valid())

    def helper_date_validation(self, EvaluationFormClass, start_date, end_date, expected_result):
        evaluation = Evaluation.objects.get()

        form_data = get_form_data_from_instance(EvaluationFormClass, evaluation)
        form_data["vote_start_datetime"] = start_date
        form_data["vote_end_date"] = end_date

        if EvaluationFormClass == EvaluationForm:
            form = EvaluationForm(form_data, instance=evaluation, semester=evaluation.course.semester)
        else:
            form = EvaluationFormClass(form_data, instance=evaluation)
        self.assertEqual(form.is_valid(), expected_result)

    def test_contributor_evaluation_form_date_validation(self):
        """
            Tests validity of various start/end date combinations in
            the two evaluation edit forms.
        """
        evaluation = baker.make(Evaluation)
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        # contributors: start date does not have to be in the future
        self.helper_date_validation(ContributorEvaluationForm, "1999-01-01", "2099-01-01", True)

        # contributors: end date must be in the future
        self.helper_date_validation(ContributorEvaluationForm, "2099-01-01", "1999-01-01", False)

        # contributors: start date must be < end date
        self.helper_date_validation(ContributorEvaluationForm, "2099-01-01", "2098-01-01", False)

        # contributors: valid data
        self.helper_date_validation(ContributorEvaluationForm, "2098-01-01", "2099-01-01", True)

        # staff: neither end nor start date must be in the future
        self.helper_date_validation(EvaluationForm, "1998-01-01", "1999-01-01", True)

        # staff: valid data in the future
        self.helper_date_validation(EvaluationForm, "2098-01-01", "2099-01-01", True)

        # staff: but start date must be < end date
        self.helper_date_validation(EvaluationForm, "1999-01-01", "1998-01-01", False)

    def test_uniqueness_constraint_error_shown(self):
        """
            Tests whether errors being caused by a uniqueness constraint are shown in the form
        """
        course = baker.make(Course)
        evaluation1 = baker.make(Evaluation, course=course, name_de="Evaluierung 1", name_en="Evaluation 1")
        evaluation2 = baker.make(Evaluation, course=course, name_de="Evaluierung 2", name_en="Evaluation 2")

        form_data = get_form_data_from_instance(EvaluationForm, evaluation2)
        form_data["name_de"] = evaluation1.name_de
        form = EvaluationForm(form_data, instance=evaluation2, semester=evaluation2.course.semester)

        self.assertFalse(form.is_valid())
        self.assertIn('name_de', form.errors)
        self.assertEqual(form.errors['name_de'], ['Evaluation with this Course and Name (german) already exists.'])

    def test_voter_cannot_be_removed_from_evaluation(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, course=baker.make(Course, degrees=[baker.make(Degree)]), participants=[student], voters=[student])
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        form_data = get_form_data_from_instance(EvaluationForm, evaluation)
        form_data["participants"] = []
        form = EvaluationForm(form_data, instance=evaluation, semester=evaluation.course.semester)

        self.assertFalse(form.is_valid())
        self.assertIn('participants', form.errors)
        self.assertIn("Participants who already voted for the evaluation can't be removed", form.errors['participants'][0])

    def test_course_change_updates_cache(self):
        semester = baker.make(Semester)
        course1 = baker.make(Course, semester=semester)
        course2 = baker.make(Course, semester=semester)
        evaluation = baker.make(Evaluation, course=course1)
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        form_data = get_form_data_from_instance(EvaluationForm, evaluation)
        form = EvaluationForm(form_data, instance=evaluation, semester=semester)
        self.assertTrue(form.is_valid())
        with patch('evap.results.views._delete_course_template_cache_impl') as delete_call, patch('evap.results.views.warm_up_template_cache') as warmup_call:
            # save without changes
            form.save()
            self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).course, course1)
            self.assertEqual(delete_call.call_count, 0)
            self.assertEqual(warmup_call.call_count, 0)

            # change course and save
            form_data = get_form_data_from_instance(EvaluationForm, evaluation)
            form_data["course"] = course2.pk
            form = EvaluationForm(form_data, instance=evaluation, semester=semester)
            self.assertTrue(form.is_valid())
            form.save()
            self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).course, course2)
            self.assertEqual(delete_call.call_count, 2)
            self.assertEqual(warmup_call.call_count, 2)
