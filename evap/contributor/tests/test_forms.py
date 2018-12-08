from django.forms.models import inlineformset_factory
from django.test import TestCase
from evap.contributor.forms import DelegatesForm, EditorContributionForm
from evap.evaluation.models import Contribution, Evaluation, Questionnaire, UserProfile
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

    def test_manager_only(self):
        """
            Asserts that manager_only questionnaires are shown to Editors only if
            they are already selected for a contribution of the Evaluation.
            Regression test for #593.
        """
        evaluation = mommy.make(Evaluation)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=False, manager_only=False)
        questionnaire_manager_only = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=False, manager_only=True)
        # one obsolete questionnaire that should never be shown
        mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR, obsolete=True, manager_only=False)

        # just the normal questionnaire should be shown.
        contribution1 = mommy.make(Contribution, evaluation=evaluation, contributor=mommy.make(UserProfile), questionnaires=[])

        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation})

        expected = set([questionnaire])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

        # now a manager adds a manager only questionnaire, which should be shown as well
        contribution1.questionnaires.set([questionnaire_manager_only])

        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
        formset = InlineContributionFormset(instance=evaluation, form_kwargs={'evaluation': evaluation})

        expected = set([questionnaire, questionnaire_manager_only])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

    def test_editors_cannot_degrade_responsibles(self):
        evaluation = mommy.make(Evaluation)
        user = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, evaluation=evaluation, contributor=user, responsible=True,
                                  can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)

        data = {
            "contributions-TOTAL_FORMS": 1,
            "contributions-INITIAL_FORMS": 1,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-evaluation": evaluation.pk,
            "contributions-0-order": 1,
            "contributions-0-id": contribution.pk,
            "contributions-0-contributor": user.pk,
            "contributions-0-does_not_contribute": "on",
            "contributions-0-responsibility": Contribution.IS_EDITOR,
            "contributions-0-textanswer_visibility": Contribution.OWN_TEXTANSWERS,
            "contributions-0-label": "",
            "contributions-0-DELETE": "",
        }
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        # Django guarantees that disabled fields can not be manipulated by the client
        # see https://docs.djangoproject.com/en/1.11/ref/forms/fields/#disabled
        # the form is still valid though.
        self.assertTrue(formset.forms[0].fields["responsibility"].disabled)

    def test_editors_cannot_elevate_editors(self):
        evaluation = mommy.make(Evaluation)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        contribution1 = mommy.make(Contribution, evaluation=evaluation, contributor=user1, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        contribution2 = mommy.make(Contribution, evaluation=evaluation, contributor=user2, responsible=False, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)

        data = {
            "contributions-TOTAL_FORMS": 2,
            "contributions-INITIAL_FORMS": 2,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-evaluation": evaluation.pk,
            "contributions-0-order": 1,
            "contributions-0-id": contribution1.pk,
            "contributions-0-contributor": user1.pk,
            "contributions-0-does_not_contribute": "on",
            "contributions-0-responsibility": Contribution.IS_RESPONSIBLE,
            "contributions-0-textanswer_visibility": Contribution.OWN_TEXTANSWERS,
            "contributions-0-label": "",
            "contributions-0-DELETE": "",
            "contributions-1-evaluation": evaluation.pk,
            "contributions-1-order": 1,
            "contributions-1-id": contribution2.pk,
            "contributions-1-contributor": user2.pk,
            "contributions-1-does_not_contribute": "on",
            "contributions-1-responsibility": Contribution.IS_EDITOR,
            "contributions-1-textanswer_visibility": Contribution.GENERAL_TEXTANSWERS,
            "contributions-1-label": "",
            "contributions-1-DELETE": "",
        }
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertTrue(formset.is_valid())

        data["contributions-1-responsibility"] = Contribution.IS_RESPONSIBLE
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertFalse(formset.is_valid())

    def test_editors_cannot_delete_responsibles(self):
        evaluation = mommy.make(Evaluation)
        user = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, evaluation=evaluation, contributor=user, responsible=True,
                                  can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)

        data = {
            "contributions-TOTAL_FORMS": 1,
            "contributions-INITIAL_FORMS": 1,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-evaluation": evaluation.pk,
            "contributions-0-order": 1,
            "contributions-0-id": contribution.pk,
            "contributions-0-contributor": user.pk,
            "contributions-0-does_not_contribute": "on",
            "contributions-0-responsibility": Contribution.IS_RESPONSIBLE,
            "contributions-0-textanswer_visibility": Contribution.OWN_TEXTANSWERS,
            "contributions-0-label": "",
            "contributions-0-DELETE": "",
        }
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertTrue(formset.is_valid())

        data["contributions-0-DELETE"] = 1
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertFalse(formset.is_valid())

    def test_editors_cannot_add_responsibles(self):
        evaluation = mommy.make(Evaluation)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, evaluation=evaluation, contributor=user1, responsible=True,
                                  can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)

        data = {
            "contributions-TOTAL_FORMS": 1,
            "contributions-INITIAL_FORMS": 1,
            "contributions-MIN_NUM_FORMS": 0,
            "contributions-MAX_NUM_FORMS": 1000,
            "contributions-0-DELETE": "",
            "contributions-0-evaluation": evaluation.pk,
            "contributions-0-order": 1,
            "contributions-0-id": contribution.pk,
            "contributions-0-contributor": user1.pk,
            "contributions-0-does_not_contribute": "on",
            "contributions-0-responsibility": Contribution.IS_RESPONSIBLE,
            "contributions-0-textanswer_visibility": Contribution.OWN_TEXTANSWERS,
            "contributions-0-label": "",
        }
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertTrue(formset.is_valid())

        data.update({
            "contributions-TOTAL_FORMS": 2,
            "contributions-1-DELETE": "",
            "contributions-1-evaluation": evaluation.pk,
            "contributions-1-order": 1,
            "contributions-1-id": "",
            "contributions-1-contributor": user2.pk,
            "contributions-1-does_not_contribute": "on",
            "contributions-1-responsibility": Contribution.IS_RESPONSIBLE,
            "contributions-1-textanswer_visibility": Contribution.OWN_TEXTANSWERS,
            "contributions-1-label": "",
        })
        formset = InlineContributionFormset(data, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})
        self.assertFalse(formset.is_valid())


class ContributionFormsetWebTests(WebTest):
    csrf_checks = False

    def test_form_ordering(self):
        """
            Asserts that the contribution formset is correctly sorted,
            and that an ordering changed by the user survives the reload
            when the user submits the form with errors.
            Regression test for #456.
        """
        evaluation = mommy.make(Evaluation, pk=1, state="prepared")
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        contribution1 = mommy.make(Contribution, evaluation=evaluation, contributor=user1, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS, questionnaires=[questionnaire], order=1)
        contribution2 = mommy.make(Contribution, evaluation=evaluation, contributor=user2, responsible=False, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS, questionnaires=[questionnaire], order=2)

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
        response = str(self.app.post("/contributor/evaluation/1/edit", params=data, user=user1))
        self.assertTrue(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))

        data["contributions-0-order"] = 2
        data["contributions-1-order"] = 1
        response = str(self.app.post("/contributor/evaluation/1/edit", params=data, user=user1))
        self.assertFalse(response.index("id_contributions-1-id") > response.index("id_contributions-0-id"))
