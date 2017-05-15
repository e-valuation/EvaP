from django.forms.models import inlineformset_factory
from django.test import TestCase
from evap.contributor.forms import DelegatesForm, EditorContributionForm
from evap.evaluation.models import Contribution, Course, Questionnaire, UserProfile
from evap.evaluation.tests.tools import WebTest, get_form_data_from_instance
from evap.staff.forms import ContributionFormSet
from model_mommy import mommy


class UserFormTests(TestCase):

    def test_settings_form(self):
        """
            Tests whether the settings form can be submitted without errors
        """
        user = mommy.make(UserProfile, username="testuser")
        delegate = mommy.make(UserProfile, username="delegate")

        self.assertFalse(user.delegates.filter(username="delegate").exists())

        form_data = get_form_data_from_instance(DelegatesForm, user)
        form_data["delegates"] = [delegate.pk]  # add delegate

        form = DelegatesForm(form_data, instance=user)
        self.assertTrue(form.is_valid())
        form.save()

        user = UserProfile.objects.get(username="testuser")
        self.assertTrue(user.delegates.filter(username="delegate").exists())


class ContributionFormsetTests(TestCase):

    def test_staff_only(self):
        """
            Asserts that staff_only questionnaires are shown to Editors only if
            they are already selected for a contribution of the Course.
            Regression test for #593.
        """
        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=False)
        questionnaire_staff_only = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=True)
        # one obsolete questionnaire that should never be shown
        mommy.make(Questionnaire, is_for_contributors=True, obsolete=True, staff_only=False)

        # just the normal questionnaire should be shown.
        contribution1 = mommy.make(Contribution, course=course, contributor=mommy.make(UserProfile), questionnaires=[])

        InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
        formset = InlineContributionFormset(instance=course, form_kwargs={'course': course})

        expected = set([questionnaire])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

        # now a staff member adds a staff only questionnaire, which should be shown as well
        contribution1.questionnaires.set([questionnaire_staff_only])

        InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
        formset = InlineContributionFormset(instance=course, form_kwargs={'course': course})

        expected = set([questionnaire, questionnaire_staff_only])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))


class ContributionFormsetWebTests(WebTest):
    csrf_checks = False

    def test_form_ordering(self):
        """
            Asserts that the contribution formset is correctly sorted,
            and that an ordering changed by the user survives the reload
            when the user submits the form with errors.
            Regression test for #456.
        """
        course = mommy.make(Course, pk=1, state="prepared")
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS, questionnaires=[questionnaire], order=1)
        contribution2 = mommy.make(Contribution, course=course, contributor=user2, responsible=False, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS, questionnaires=[questionnaire], order=2)

        # almost everything is missing in this set of data,
        # so we're guaranteed to have some errors
        data = {
            "contributions-TOTAL_FORMS": 2,
            "contributions-INITIAL_FORMS": 2,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-id": contribution1.id,
            "contributions-1-id": contribution2.id,
            "operation": "save"
        }

        data["contributions-0-order"] = 1
        data["contributions-1-order"] = 2
        response = str(self.app.post("/contributor/course/1/edit", data, user=user1))
        self.assertTrue(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))

        data["contributions-0-order"] = 2
        data["contributions-1-order"] = 1
        response = str(self.app.post("/contributor/course/1/edit", data, user=user1))
        self.assertFalse(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))
