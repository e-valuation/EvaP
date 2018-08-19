from django.forms.models import inlineformset_factory
from django.test import TestCase
from model_mommy import mommy

from evap.evaluation.models import UserProfile, CourseType, Course, Questionnaire, \
    Contribution, Semester, Degree, EmailTemplate, Question
from evap.evaluation.tests.tools import get_form_data_from_instance, create_course_with_responsible_and_editor, to_querydict
from evap.staff.forms import UserForm, SingleResultForm, ContributionFormSet, ContributionForm, CourseForm, \
    CourseEmailForm, QuestionnaireForm
from evap.contributor.forms import CourseForm as ContributorCourseForm


class QuestionnaireFormTest(TestCase):
    def test_force_highest_order(self):
        mommy.make(Questionnaire, order=45, type=Questionnaire.TOP)

        question = mommy.make(Question)

        data = {
            'description_de': 'English description',
            'description_en': 'German description',
            'name_de': 'A name',
            'name_en': 'A german name',
            'public_name_en': 'A display name',
            'public_name_de': 'A german display name',
            'question_set-0-id': question.id,
            'order': 0,
            'type': Questionnaire.TOP,
        }

        form = QuestionnaireForm(data=data)
        self.assertTrue(form.is_valid())
        questionnaire = form.save(force_highest_order=True)
        self.assertEqual(questionnaire.order, 46)

    def test_automatic_order_correction_on_type_change(self):
        mommy.make(Questionnaire, order=72, type=Questionnaire.BOTTOM)

        questionnaire = mommy.make(Questionnaire, order=7, type=Questionnaire.TOP)
        question = mommy.make(Question)

        data = {
            'description_de': questionnaire.description_de,
            'description_en': questionnaire.description_en,
            'name_de': questionnaire.name_de,
            'name_en': questionnaire.name_en,
            'public_name_en': questionnaire.public_name_en,
            'public_name_de': questionnaire.public_name_de,
            'question_set-0-id': question.id,
            'order': questionnaire.order,
            'type': Questionnaire.BOTTOM,
        }

        form = QuestionnaireForm(instance=questionnaire, data=data)
        self.assertTrue(form.is_valid())
        questionnaire = form.save()
        self.assertEqual(questionnaire.order, 73)


class CourseEmailFormTests(TestCase):
    def test_course_email_form(self):
        """
            Tests the CourseEmailForm with one valid and one invalid input dataset.
        """
        course = create_course_with_responsible_and_editor()
        mommy.make(Contribution, course=course)
        data = {"body": "wat", "subject": "some subject", "recipients": [EmailTemplate.DUE_PARTICIPANTS]}
        form = CourseEmailForm(course=course, data=data)
        self.assertTrue(form.is_valid())
        form.send(None)

        data = {"body": "wat", "subject": "some subject"}
        form = CourseEmailForm(course=course, data=data)
        self.assertFalse(form.is_valid())


class UserFormTests(TestCase):
    def test_user_form(self):
        """
            Tests the UserForm with one valid and one invalid input dataset.
        """
        user = mommy.make(UserProfile)
        another_user = mommy.make(UserProfile)
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
        user = mommy.make(UserProfile, email="uiae@example.com")

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
        user = mommy.make(UserProfile)

        data = {"username": user.username}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

    def test_user_cannot_be_removed_from_course_already_voted_for(self):
        student = mommy.make(UserProfile)
        mommy.make(Course, participants=[student], voters=[student])

        form_data = get_form_data_from_instance(UserForm, student)
        form_data["courses_participating_in"] = []
        form = UserForm(form_data, instance=student)

        self.assertFalse(form.is_valid())
        self.assertIn('courses_participating_in', form.errors)
        self.assertIn("Courses for which the user already voted can't be removed", form.errors['courses_participating_in'][0])


class SingleResultFormTests(TestCase):
    def test_single_result_form_saves_participant_and_voter_count(self):
        responsible = mommy.make(UserProfile)
        course_type = mommy.make(CourseType)
        course = Course(semester=mommy.make(Semester), is_single_result=True)
        form_data = {
            "name_de": "qwertz",
            "name_en": "qwertz",
            "type": course_type.pk,
            "degrees": [1],
            "event_date": "2014-01-01",
            "responsible": responsible.pk,
            "answer_1": 6,
            "answer_2": 0,
            "answer_3": 2,
            "answer_4": 0,
            "answer_5": 2,
            "semester": course.semester.pk
        }
        form = SingleResultForm(form_data, instance=course)
        self.assertTrue(form.is_valid())

        form.save(user=mommy.make(UserProfile))

        course = Course.objects.get()
        self.assertEqual(course.num_participants, 10)
        self.assertEqual(course.num_voters, 10)

    def test_single_result_form_can_change_responsible(self):
        responsible = mommy.make(UserProfile)
        course_type = mommy.make(CourseType)
        course = Course(semester=mommy.make(Semester), is_single_result=True)
        form_data = {
            "name_de": "qwertz",
            "name_en": "qwertz",
            "type": course_type.pk,
            "degrees": [1],
            "event_date": "2014-01-01",
            "responsible": responsible.pk,
            "answer_1": 6,
            "answer_2": 0,
            "answer_3": 2,
            "answer_4": 0,
            "answer_5": 2,
            "semester": course.semester.pk
        }
        form = SingleResultForm(form_data, instance=course)
        self.assertTrue(form.is_valid())

        form.save(user=mommy.make(UserProfile))
        self.assertEqual(course.responsible_contributors[0], responsible)

        new_responsible = mommy.make(UserProfile)
        form_data["responsible"] = new_responsible.pk
        form = SingleResultForm(form_data, instance=course)
        self.assertTrue(form.is_valid())

        form.save(user=mommy.make(UserProfile))
        self.assertEqual(course.responsible_contributors[0], new_responsible)


class ContributionFormsetTests(TestCase):
    def test_contribution_form_set(self):
        """
            Tests the ContributionFormset with various input data sets.
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-0-comment_visibility': Contribution.ALL_COMMENTS,
        })
        # no contributor and no responsible
        self.assertFalse(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data.copy()).is_valid())
        # valid
        data['contributions-0-contributor'] = user1.pk
        self.assertTrue(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data.copy()).is_valid())
        # duplicate contributor
        data['contributions-TOTAL_FORMS'] = 2
        data['contributions-1-contributor'] = user1.pk
        data['contributions-1-course'] = course.pk
        data['contributions-1-questionnaires'] = questionnaire.pk
        data['contributions-1-order'] = 1
        data['contributions-1-comment_visibility'] = Contribution.ALL_COMMENTS
        self.assertFalse(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data).is_valid())
        # two responsibles
        data['contributions-1-contributor'] = user2.pk
        data['contributions-1-responsibility'] = Contribution.IS_RESPONSIBLE
        self.assertTrue(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data).is_valid())

    def test_dont_validate_deleted_contributions(self):
        """
            Tests whether contributions marked for deletion are validated.
            Regression test for #415 and #244
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        # Here we have two responsibles (one of them deleted with no questionnaires), and a deleted contributor with no questionnaires.

        data = to_querydict({
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': "",
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-0-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-0-contributor': user1.pk,
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-1-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-1-contributor': user2.pk,
            'contributions-2-course': course.pk,
            'contributions-2-questionnaires': "",
            'contributions-2-order': 1,
            'contributions-2-responsibility': "CONTRIBUTOR",
            'contributions-2-comment_visibility': Contribution.OWN_COMMENTS,
            'contributions-2-contributor': user2.pk,
        })

        # Without deletion, this form should be invalid
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertFalse(formset.is_valid())

        data['contributions-0-DELETE'] = 'on'
        data['contributions-2-DELETE'] = 'on'

        # With deletion, it should be valid
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_deleted_empty_contribution_does_not_crash(self):
        """
            When removing the empty extra contribution formset, validating the form should not crash.
            Similarly, when removing the contribution formset of an existing contributor, and entering some data in the extra formset, it should not crash.
            Regression test for #1057
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-0-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-0-contributor': user1.pk,
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': "",
            'contributions-1-order': -1,
            'contributions-1-responsibility': "CONTRIBUTOR",
            'contributions-1-comment_visibility': Contribution.OWN_COMMENTS,
            'contributions-1-contributor': "",
        })

        # delete extra formset
        data['contributions-1-DELETE'] = 'on'
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        formset.is_valid()
        data['contributions-1-DELETE'] = ''

        # delete first, change data in extra formset
        data['contributions-0-DELETE'] = 'on'
        data['contributions-1-responsibility'] = Contribution.IS_RESPONSIBLE
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        formset.is_valid()

    def test_take_deleted_contributions_into_account(self):
        """
            Tests whether contributions marked for deletion are properly taken into account
            when the same contributor got added again in the same formset.
            Regression test for #415
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True,
                                   comment_visibility=Contribution.ALL_COMMENTS, questionnaires=[questionnaire])

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-0-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-id': '',
            'contributions-1-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-1-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-1-contributor': user1.pk,
        })

        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_obsolete_manager_only(self):
        """
            Asserts that obsolete questionnaires are shown to managers only if
            they are already selected for a contribution of the Course, and
            that manager only questionnaires are always shown.
            Regression test for #593.
        """
        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=False, manager_only=False)
        questionnaire_obsolete = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=True, manager_only=False)
        questionnaire_manager_only = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=False, manager_only=True)

        # The normal and manager_only questionnaire should be shown.
        contribution1 = mommy.make(Contribution, course=course, contributor=mommy.make(UserProfile), questionnaires=[])

        inline_contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=course, form_kwargs={'course': course})

        expected = {questionnaire, questionnaire_manager_only}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

        # Suppose we had an obsolete questionnaire already selected, that should be shown as well.
        contribution1.questionnaires.set([questionnaire_obsolete])

        inline_contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=course, form_kwargs={'course': course})

        expected = {questionnaire, questionnaire_manager_only, questionnaire_obsolete}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))


class ContributionFormset775RegressionTests(TestCase):
    """
        Various regression tests for #775
    """
    @classmethod
    def setUpTestData(cls):
        cls.course = mommy.make(Course, name_en="some course")
        cls.user1 = mommy.make(UserProfile)
        cls.user2 = mommy.make(UserProfile)
        mommy.make(UserProfile)
        cls.questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        cls.contribution1 = mommy.make(Contribution, responsible=True, contributor=cls.user1, course=cls.course, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.user2, course=cls.course)

        cls.contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

    def setUp(self):
        self.data = to_querydict({
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 2,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': str(self.contribution1.pk),  # browsers send strings so we should too
            'contributions-0-course': self.course.pk,
            'contributions-0-questionnaires': self.questionnaire.pk,
            'contributions-0-order': 0,
            'contributions-0-responsibility': Contribution.IS_RESPONSIBLE,
            'contributions-0-comment_visibility': Contribution.ALL_COMMENTS,
            'contributions-0-contributor': self.user1.pk,
            'contributions-1-id': str(self.contribution2.pk),
            'contributions-1-course': self.course.pk,
            'contributions-1-questionnaires': self.questionnaire.pk,
            'contributions-1-order': 0,
            'contributions-1-responsibility': "CONTRIBUTOR",
            'contributions-1-comment_visibility': Contribution.OWN_COMMENTS,
            'contributions-1-contributor': self.user2.pk,
        })

    def test_swap_contributors(self):
        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
        self.assertTrue(formset.is_valid())

        # swap contributors, should still be valid
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk
        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
        self.assertTrue(formset.is_valid())

    def test_move_and_delete(self):
        # move contributor2 to the first contribution and delete the second one
        # after saving, only one contribution should exist and have the contributor2
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user2.pk
        self.data['contributions-1-DELETE'] = 'on'
        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
        self.assertTrue(formset.is_valid())
        formset.save()
        self.assertTrue(Contribution.objects.filter(contributor=self.user2, course=self.course).exists())
        self.assertFalse(Contribution.objects.filter(contributor=self.user1, course=self.course).exists())

    def test_extra_form(self):
        # make sure nothing crashes when an extra form is present.
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk
        self.data['contributions-TOTAL_FORMS'] = 3
        self.data['contributions-2-id'] = ""
        self.data['contributions-2-order'] = -1
        self.data['contributions-2-responsibility'] = "CONTRIBUTOR"
        self.data['contributions-2-comment_visibility'] = Contribution.OWN_COMMENTS
        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
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
        self.data['contributions-1-comment_visibility'] = Contribution.OWN_COMMENTS

        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
        self.assertTrue(formset.is_valid())

    def test_handle_multivaluedicts(self):
        # make sure the workaround is not eating questionnaires
        # first, swap contributors to trigger the workaround
        self.data['contributions-0-contributor'] = self.user2.pk
        self.data['contributions-1-contributor'] = self.user1.pk

        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        self.data.appendlist('contributions-0-questionnaires', questionnaire.pk)
        formset = self.contribution_formset(instance=self.course, form_kwargs={'course': self.course}, data=self.data)
        formset.save()
        self.assertEqual(Questionnaire.objects.filter(contributions=self.contribution2).count(), 2)


class CourseFormTests(TestCase):
    def helper_test_course_form_same_name(self, CourseFormClass):
        courses = Course.objects.all()

        form_data = get_form_data_from_instance(CourseForm, courses[0])
        form_data["vote_start_datetime"] = "2098-01-01"  # needed to fix the form
        form_data["vote_end_date"] = "2099-01-01"  # needed to fix the form

        form = CourseFormClass(form_data, instance=courses[0])
        self.assertTrue(form.is_valid())
        form_data['name_de'] = courses[1].name_de
        form = CourseFormClass(form_data, instance=courses[0])
        self.assertFalse(form.is_valid())

    def test_course_form_same_name(self):
        """
            Test whether giving a course the same name as another course
            in the same semester in the course edit form is invalid.
        """
        courses = mommy.make(Course, semester=mommy.make(Semester), degrees=[mommy.make(Degree)], _quantity=2)
        courses[0].general_contribution.questionnaires.set([mommy.make(Questionnaire)])
        courses[1].general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        self.helper_test_course_form_same_name(CourseForm)
        self.helper_test_course_form_same_name(ContributorCourseForm)

    def helper_date_validation(self, CourseFormClass, start_date, end_date, expected_result):
        course = Course.objects.get()

        form_data = get_form_data_from_instance(CourseFormClass, course)
        form_data["vote_start_datetime"] = start_date
        form_data["vote_end_date"] = end_date

        form = CourseFormClass(form_data, instance=course)
        self.assertEqual(form.is_valid(), expected_result)

    def test_contributor_course_form_date_validation(self):
        """
            Tests validity of various start/end date combinations in
            the two course edit forms.
        """
        course = mommy.make(Course, degrees=[mommy.make(Degree)])
        course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        # contributors: start date must be in the future
        self.helper_date_validation(ContributorCourseForm, "1999-01-01", "2099-01-01", False)

        # contributors: end date must be in the future
        self.helper_date_validation(ContributorCourseForm, "2099-01-01", "1999-01-01", False)

        # contributors: start date must be < end date
        self.helper_date_validation(ContributorCourseForm, "2099-01-01", "2098-01-01", False)

        # contributors: valid data
        self.helper_date_validation(ContributorCourseForm, "2098-01-01", "2099-01-01", True)

        # staff: neither end nor start date must be in the future
        self.helper_date_validation(CourseForm, "1998-01-01", "1999-01-01", True)

        # staff: valid data in the future
        self.helper_date_validation(CourseForm, "2098-01-01", "2099-01-01", True)

        # staff: but start date must be < end date
        self.helper_date_validation(CourseForm, "1999-01-01", "1998-01-01", False)

    def test_uniqueness_constraint_error_shown(self):
        """
            Tests whether errors being caused by a uniqueness constraint are shown in the form
        """
        semester = mommy.make(Semester)
        course1 = mommy.make(Course, semester=semester)
        course2 = mommy.make(Course, semester=semester)

        form_data = get_form_data_from_instance(CourseForm, course2)
        form_data["name_de"] = course1.name_de
        form = CourseForm(form_data, instance=course2)

        self.assertFalse(form.is_valid())
        self.assertIn('name_de', form.errors)
        self.assertEqual(form.errors['name_de'], ['Course with this Semester and Name (german) already exists.'])

    def test_voter_cannot_be_removed_from_course(self):
        student = mommy.make(UserProfile)
        course = mommy.make(Course, degrees=[mommy.make(Degree)], participants=[student], voters=[student])
        course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        form_data = get_form_data_from_instance(CourseForm, course)
        form_data["participants"] = []
        form = CourseForm(form_data, instance=course)

        self.assertFalse(form.is_valid())
        self.assertIn('participants', form.errors)
        self.assertIn("Participants who already voted for the course can't be removed", form.errors['participants'][0])
