from django.forms.models import inlineformset_factory
from django.test import TestCase
from model_mommy import mommy

from evap.evaluation.models import UserProfile, CourseType, Course, Questionnaire, Contribution, Semester, Degree
from evap.evaluation.tests.test_utils import get_form_data_from_instance, course_with_responsible_and_editor
from evap.staff.forms import UserForm, SingleResultForm, ContributionFormSet, ContributionForm, CourseForm, \
    CourseEmailForm
from evap.contributor.forms import CourseForm as ContributorCourseForm


class CourseEmailFormTests(TestCase):
    def test_course_email_form(self):
        """
            Tests the CourseEmailForm with one valid and one invalid input dataset.
        """
        course = course_with_responsible_and_editor()
        mommy.make(Contribution, course=course)
        data = {"body": "wat", "subject": "some subject", "recipients": ["due_participants"]}
        form = CourseEmailForm(instance=course, data=data)
        self.assertTrue(form.is_valid())
        self.assertTrue(form.missing_email_addresses() == 0)
        form.send()

        data = {"body": "wat", "subject": "some subject"}
        form = CourseEmailForm(instance=course, data=data)
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


class SingleResultFormTests(TestCase):
    def test_single_result_form_saves_participant_and_voter_count(self):
        responsible = mommy.make(UserProfile)
        course_type = mommy.make(CourseType)
        form_data = {
            "name_de": "qwertz",
            "name_en": "qwertz",
            "type": course_type.pk,
            "degrees": ["1"],
            "event_date": "02/1/2014",
            "responsible": responsible.pk,
            "answer_1": 6,
            "answer_2": 0,
            "answer_3": 2,
            "answer_4": 0,
            "answer_5": 2,
        }
        course = Course(semester=mommy.make(Semester))
        form = SingleResultForm(form_data, instance=course)
        self.assertTrue(form.is_valid())

        form.save(user=mommy.make(UserProfile))

        course = Course.objects.get()
        self.assertEqual(course.num_participants, 10)
        self.assertEqual(course.num_voters, 10)


class ContributionFormsetTests(TestCase):
    def test_dont_validate_deleted_contributions(self):
        """
            Tests whether contributions marked for deletion are validated.
            Regression test for #415 and #244
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        # Here we have two responsibles (one of them deleted), and a deleted contributor with no questionnaires.
        data = {
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsibility': "RESPONSIBLE",
            'contributions-1-comment_visibility': "ALL",
            'contributions-1-contributor': user2.pk,
            'contributions-2-course': course.pk,
            'contributions-2-questionnaires': [],
            'contributions-2-order': 1,
            'contributions-2-responsibility': "CONTRIBUTOR",
            'contributions-2-comment_visibility': "OWN",
            'contributions-2-contributor': user2.pk,
            'contributions-2-DELETE': 'on',
        }

        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_take_deleted_contributions_into_account(self):
        """
            Tests whether contributions marked for deletion are properly taken into account
            when the same contributor got added again in the same formset.
            Regression test for #415
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True,
                                   comment_visibility=Contribution.ALL_COMMENTS, questionnaires=[questionnaire])

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = {
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsibility': "RESPONSIBLE",
            'contributions-1-comment_visibility': "ALL",
            'contributions-1-contributor': user1.pk,
        }

        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_swapping_contributors(self):
        """
            Asserts that the user can swap the contributors of two contributions.
            Regression test for #775
        """
        course = mommy.make(Course, name_en="some course")
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)
        contribution1 = mommy.make(Contribution, responsible=True, contributor=user1, course=course)
        contribution2 = mommy.make(Contribution, contributor=user2, course=course)

        contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = {
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 2,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
            'contributions-0-contributor': user1.pk,
            'contributions-1-id': contribution2.pk,
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsibility': "CONTRIBUTOR",
            'contributions-1-comment_visibility': "ALL",
            'contributions-1-contributor': user2.pk,
            'contributions-2-id': "", # the extra form triggers another edge case
            'contributions-2-order': -1,
            'contributions-2-responsibility': "CONTRIBUTOR",
            'contributions-2-comment_visibility': "OWN",
        }

        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

        # swap contributors, should still be valid
        data['contributions-0-contributor'] = user2.pk
        data['contributions-1-contributor'] = user1.pk
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

        # now just move contributor2 to the first contribution and delete the second one
        # after saving, only one contribution should exist and have the contributor2
        data['contributions-0-contributor'] = user2.pk
        data['contributions-1-contributor'] = user2.pk
        data['contributions-1-DELETE'] = 'on'
        formset = contribution_formset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())
        formset.save()
        self.assertTrue(Contribution.objects.filter(contributor=user2, course=course).exists())
        self.assertFalse(Contribution.objects.filter(contributor=user1, course=course).exists())

    def test_obsolete_staff_only(self):
        """
            Asserts that obsolete questionnaires are shown to staff members only if
            they are already selected for a contribution of the Course, and
            that staff_only questionnaires are always shown.
            Regression test for #593.
        """
        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=False)
        questionnaire_obsolete = mommy.make(Questionnaire, is_for_contributors=True, obsolete=True, staff_only=False)
        questionnaire_staff_only = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=True)

        # The normal and staff_only questionnaire should be shown.
        contribution1 = mommy.make(Contribution, course=course, contributor=mommy.make(UserProfile), questionnaires=[])

        inline_contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=course, form_kwargs={'course': course})

        expected = {questionnaire, questionnaire_staff_only}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

        # Suppose we had an obsolete questionnaire already selected, that should be shown as well.
        contribution1.questionnaires = [questionnaire_obsolete]

        inline_contribution_formset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = inline_contribution_formset(instance=course, form_kwargs={'course': course})

        expected = {questionnaire, questionnaire_staff_only, questionnaire_obsolete}
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))


class CourseFormTests(TestCase):
    def helper_test_course_form_same_name(self, CourseFormClass):
        courses = Course.objects.all()

        form_data = get_form_data_from_instance(CourseForm, courses[0])
        form_data["vote_start_date"] = "02/1/2098" # needed to fix the form
        form_data["vote_end_date"] = "02/1/2099" # needed to fix the form

        form = CourseForm(form_data, instance=courses[0])
        self.assertTrue(form.is_valid())
        form_data['name_de'] = courses[1].name_de
        form = CourseForm(form_data, instance=courses[0])
        self.assertFalse(form.is_valid())

    def test_course_form_same_name(self):
        """
            Test whether giving a course the same name as another course
            in the same semester in the course edit form is invalid.
        """
        courses = mommy.make(Course, semester=mommy.make(Semester), degrees=[mommy.make(Degree)], _quantity=2)
        courses[0].general_contribution.questionnaires = [mommy.make(Questionnaire)]
        courses[1].general_contribution.questionnaires = [mommy.make(Questionnaire)]

        self.helper_test_course_form_same_name(CourseForm)
        self.helper_test_course_form_same_name(ContributorCourseForm)

    def helper_date_validation(self, CourseFormClass, start_date, end_date, expected_result):
        course = Course.objects.get()

        form_data = get_form_data_from_instance(CourseFormClass, course)
        form_data["vote_start_date"] = start_date
        form_data["vote_end_date"] = end_date

        form = CourseFormClass(form_data, instance=course)
        self.assertEqual(form.is_valid(), expected_result)

    def test_contributor_course_form_date_validation(self):
        """
            Tests validity of various start/end date combinations in
            the two course edit forms.
        """
        course = mommy.make(Course, degrees=[mommy.make(Degree)])
        course.general_contribution.questionnaires = [mommy.make(Questionnaire)]

        # contributors: start date must be in the future
        self.helper_date_validation(ContributorCourseForm, "02/1/1999", "02/1/2099", False)

        # contributors: end date must be in the future
        self.helper_date_validation(ContributorCourseForm, "02/1/2099", "02/1/1999", False)

        # contributors: start date must be < end date
        self.helper_date_validation(ContributorCourseForm, "02/1/2099", "02/1/2098", False)

        # contributors: valid data
        self.helper_date_validation(ContributorCourseForm, "02/1/2098", "02/1/2099", True)

        # staff: neither end nor start date must be in the future
        self.helper_date_validation(CourseForm, "02/1/1998", "02/1/1999", True)

        # staff: valid data in the future
        self.helper_date_validation(CourseForm, "02/1/2098", "02/1/2099", True)

        # staff: but start date must be < end date
        self.helper_date_validation(CourseForm, "02/1/1999", "02/1/1998", False)
