import datetime
from fractions import Fraction
from functools import partial

from django.test.utils import override_settings
from model_bakery import baker

from evap.evaluation.models import (
    Answer,
    Contribution,
    Evaluation,
    Question,
    Questionnaire,
    QuestionType,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
    VoteTimestamp,
)
from evap.evaluation.tests.tools import FuzzyInt, WebTest, WebTestWith200Check, render_pages
from evap.student.tools import answer_field_id
from evap.student.views import SUCCESS_MAGIC_STRING


class TestStudentIndexView(WebTestWith200Check):
    url = "/student/"

    @classmethod
    def setUpTestData(cls):
        # View is only visible to users participating in at least one evaluation.
        cls.user = baker.make(UserProfile, email="student@institution.example.com")
        cls.semester = baker.make(Semester, is_active=True)
        cls.evaluation = baker.make(Evaluation, course__semester=cls.semester, participants=[cls.user])

        cls.test_users = [cls.user]

    def test_num_queries_is_constant(self):
        semester1 = baker.make(Semester)
        semester2 = baker.make(Semester, participations_are_archived=True)

        for semester in [semester1, semester2]:
            evaluations = baker.make(
                Evaluation,
                course__semester=semester,
                state=Evaluation.State.PUBLISHED,
                _quantity=100,
                _bulk_create=True,
            )
            participations = [Evaluation.participants.through(evaluation=e, userprofile=self.user) for e in evaluations]
            Evaluation.participants.through.objects.bulk_create(participations)

        with self.assertNumQueries(FuzzyInt(0, 100)):
            self.app.get(self.url, user=self.user)

    @override_settings(
        GLOBAL_EVALUATION_PROGRESS_REWARDS=[(Fraction(1, 10), "a dog"), (Fraction(5, 10), "a quokka")],
        GLOBAL_EVALUATION_PROGRESS_INFO_TEXT={"de": "info_text_str", "en": "info_text_str"},
        GLOBAL_EVALUATION_PROGRESS_EXCLUDED_COURSE_TYPE_IDS=[1042],
        GLOBAL_EVALUATION_PROGRESS_EXCLUDED_EVALUATION_IDS=[1043],
    )
    def test_global_reward_progress(self):
        excluded_states = [state for state in Evaluation.State if state < Evaluation.State.APPROVED]
        included_states = [state for state in Evaluation.State if state >= Evaluation.State.APPROVED]

        users = baker.make(UserProfile, _quantity=20, _bulk_create=True)
        make_evaluation = partial(
            baker.make,
            Evaluation,
            course__semester=self.semester,
            participants=users,
            voters=users[:10],
            state=Evaluation.State.APPROVED,
        )

        # excluded
        make_evaluation(is_rewarded=False)
        make_evaluation(is_single_result=True)
        make_evaluation(course__is_private=True)
        make_evaluation(id=1043)
        make_evaluation(course__type__id=1042)
        make_evaluation(_quantity=len(excluded_states), state=iter(excluded_states))

        # included
        included_evaluations = [
            *make_evaluation(_quantity=len(included_states), state=iter(included_states)),
            make_evaluation(_voter_count=123, _participant_count=456),
        ]

        baker.make(VoteTimestamp, evaluation=included_evaluations[0])

        expected_participants = sum(e.num_participants for e in included_evaluations)
        expected_voters = sum(e.num_voters for e in included_evaluations)
        expected_voter_percent = 100 * expected_voters // expected_participants

        page = self.app.get(self.url, user=self.user)
        self.assertIn("Fundraising", page)
        self.assertIn("info_text_str", page)
        self.assertIn("Last evaluation:", page)
        self.assertIn(f"{expected_voters} submitted evaluations ({expected_voter_percent}%)", page)
        self.assertIn("a quokka", page)
        self.assertIn("10%", page)
        self.assertIn("a dog", page)
        self.assertIn("50%", page)

    @override_settings(GLOBAL_EVALUATION_PROGRESS_REWARDS=[(Fraction("0.07"), "a dog")])
    def test_global_reward_progress_edge_cases(self):
        # no active semester
        Semester.objects.update(is_active=False)
        page = self.app.get(self.url, user=self.user)
        self.assertNotIn("7%", page)
        self.assertNotIn("a dog", page)

        # no voters / participants -> possibly zero division
        # also: no last vote timestamp
        semester = baker.make(Semester, is_active=True)
        page = self.app.get(self.url, user=self.user)
        self.assertNotIn("Last evaluation:", page)
        self.assertIn("0 submitted evaluations (0%)", page)
        self.assertIn("7%", page)
        self.assertIn("a dog", page)

        # more voters than required for last reward
        baker.make(
            Evaluation,
            course__semester=semester,
            _voter_count=89,
            _participant_count=97,
            state=Evaluation.State.EVALUATED,
        )
        page = self.app.get(self.url, user=self.user)
        self.assertIn("89 submitted evaluations (91%)", page)  # 91% is intentionally rounded down
        self.assertIn("7%", page)
        self.assertIn("a dog", page)

    @override_settings(
        GLOBAL_EVALUATION_PROGRESS_REWARDS=[],
        GLOBAL_EVALUATION_PROGRESS_INFO_TEXT={"de": "info_text_str", "en": "info_text_str"},
    )
    def test_global_reward_progress_hidden(self):
        page = self.app.get(self.url, user=self.user)
        self.assertNotIn("Fundraising", page)
        self.assertNotIn("info_text_str", page)


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestVoteView(WebTest):
    render_pages_url = "/student/vote/PK"

    @classmethod
    def setUpTestData(cls):
        cls.voting_user1 = baker.make(UserProfile, email="voting_user1@institution.example.com")
        cls.voting_user2 = baker.make(UserProfile, email="voting_user2@institution.example.com")
        cls.contributor1 = baker.make(UserProfile, email="contributor1@institution.example.com")
        cls.contributor2 = baker.make(UserProfile, email="contributor2@institution.example.com")

        cls.evaluation = baker.make(
            Evaluation,
            participants=[cls.voting_user1, cls.voting_user2, cls.contributor1],
            state=Evaluation.State.IN_EVALUATION,
        )
        cls.url = f"/student/vote/{cls.evaluation.pk}"

        cls.top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.bottom_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM)
        cls.contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

        cls.contributor_heading_question = baker.make(
            Question, questionnaire=cls.contributor_questionnaire, order=0, type=QuestionType.HEADING
        )
        cls.contributor_text_question = baker.make(
            Question, questionnaire=cls.contributor_questionnaire, order=1, type=QuestionType.TEXT
        )
        cls.contributor_likert_question = baker.make(
            Question, questionnaire=cls.contributor_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT
        )

        cls.top_heading_question = baker.make(
            Question, questionnaire=cls.top_general_questionnaire, order=0, type=QuestionType.HEADING
        )
        cls.top_text_question = baker.make(
            Question, questionnaire=cls.top_general_questionnaire, order=1, type=QuestionType.TEXT
        )
        cls.top_likert_question = baker.make(
            Question, questionnaire=cls.top_general_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT
        )
        cls.top_grade_question = baker.make(
            Question, questionnaire=cls.top_general_questionnaire, order=3, type=QuestionType.GRADE
        )

        cls.bottom_heading_question = baker.make(
            Question, questionnaire=cls.bottom_general_questionnaire, order=0, type=QuestionType.HEADING
        )
        cls.bottom_text_question = baker.make(
            Question, questionnaire=cls.bottom_general_questionnaire, order=1, type=QuestionType.TEXT
        )
        cls.bottom_likert_question = baker.make(
            Question, questionnaire=cls.bottom_general_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT
        )
        cls.bottom_grade_question = baker.make(
            Question, questionnaire=cls.bottom_general_questionnaire, order=3, type=QuestionType.GRADE
        )

        cls.contribution1 = baker.make(
            Contribution,
            contributor=cls.contributor1,
            questionnaires=[cls.contributor_questionnaire],
            evaluation=cls.evaluation,
        )
        cls.contribution2 = baker.make(
            Contribution,
            contributor=cls.contributor2,
            questionnaires=[cls.contributor_questionnaire],
            evaluation=cls.evaluation,
        )

        cls.evaluation.general_contribution.questionnaires.set(
            [cls.top_general_questionnaire, cls.bottom_general_questionnaire]
        )

    @render_pages
    def render_pages(self):
        with_confirmation = self.app.get(self.url, user=self.voting_user1)
        submit_errors = with_confirmation.forms["student-vote-form"].submit()

        with override_settings(SMALL_COURSE_SIZE=2):
            normal = self.app.get(self.url, user=self.voting_user1)

        return {
            "with_textanswer_publish_confirmation": with_confirmation.content,
            "submit_errors": submit_errors.content,
            "normal": normal.content,
        }

    def test_question_ordering(self):
        page = self.app.get(self.url, user=self.voting_user1, status=200)

        top_heading_index = page.body.decode().index(self.top_heading_question.text)
        top_text_index = page.body.decode().index(self.top_text_question.text)

        contributor_heading_index = page.body.decode().index(self.contributor_heading_question.text)
        contributor_likert_index = page.body.decode().index(self.contributor_likert_question.text)

        bottom_heading_index = page.body.decode().index(self.bottom_heading_question.text)
        bottom_grade_index = page.body.decode().index(self.bottom_grade_question.text)

        self.assertTrue(
            top_heading_index
            < top_text_index
            < contributor_heading_index
            < contributor_likert_index
            < bottom_heading_index
            < bottom_grade_index
        )

    def fill_form(self, form, fill_general_complete=True, fill_contributors_complete=True):
        contribution = self.evaluation.general_contribution
        questionnaire = self.top_general_questionnaire
        form[answer_field_id(contribution, questionnaire, self.top_text_question)] = "some text"
        form[answer_field_id(contribution, questionnaire, self.top_grade_question)] = 3
        form[answer_field_id(contribution, questionnaire, self.top_likert_question)] = 1
        form[answer_field_id(contribution, questionnaire, self.top_likert_question, additional_textanswer=True)] = (
            "some additional text"
        )

        questionnaire = self.bottom_general_questionnaire
        form[answer_field_id(contribution, questionnaire, self.bottom_text_question)] = "some bottom text"
        form[answer_field_id(contribution, questionnaire, self.bottom_grade_question)] = 4
        if fill_general_complete:
            form[answer_field_id(contribution, questionnaire, self.bottom_likert_question)] = 2

        contribution = self.contribution1
        questionnaire = self.contributor_questionnaire
        form[answer_field_id(contribution, questionnaire, self.contributor_text_question)] = "some other text"
        form[answer_field_id(contribution, questionnaire, self.contributor_likert_question)] = 4
        form[
            answer_field_id(contribution, questionnaire, self.contributor_likert_question, additional_textanswer=True)
        ] = "some other additional text"

        contribution = self.contribution2
        form[answer_field_id(contribution, questionnaire, self.contributor_text_question)] = "some more text"
        if fill_contributors_complete:
            form[answer_field_id(contribution, questionnaire, self.contributor_likert_question)] = 2

    def test_incomplete_general_vote_form(self):
        """
        Submits a student vote, verifies that an error message is displayed if not all general rating questions have
        been answered and that all given answers stay selected/filled.
        """
        page = self.app.get(self.url, user=self.voting_user1.email, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_general_complete=False)
        response = form.submit(status=200)
        self.assertIn("vote for all rating questions", response)
        self.assertNotIn("skip the questions about a single person", response)

        form = page.forms["student-vote-form"]

        field_id = partial(answer_field_id, self.evaluation.general_contribution, self.top_general_questionnaire)
        self.assertEqual(form[field_id(self.top_text_question)].value, "some text")
        self.assertEqual(form[field_id(self.top_likert_question)].value, "1")
        self.assertEqual(
            form[field_id(self.top_likert_question, additional_textanswer=True)].value, "some additional text"
        )
        self.assertEqual(form[field_id(self.top_grade_question)].value, "3")

        field_id = partial(answer_field_id, self.evaluation.general_contribution, self.bottom_general_questionnaire)
        self.assertEqual(form[field_id(self.bottom_text_question)].value, "some bottom text")
        self.assertEqual(form[field_id(self.bottom_grade_question)].value, "4")

        field_id = partial(answer_field_id, self.contribution1, self.contributor_questionnaire)
        self.assertEqual(form[field_id(self.contributor_text_question)].value, "some other text")
        self.assertEqual(form[field_id(self.contributor_likert_question)].value, "4")
        self.assertEqual(
            form[field_id(self.contributor_likert_question, additional_textanswer=True)].value,
            "some other additional text",
        )

        field_id = partial(answer_field_id, self.contribution2, self.contributor_questionnaire)
        self.assertEqual(form[field_id(self.contributor_text_question)].value, "some more text")
        self.assertEqual(form[field_id(self.contributor_likert_question)].value, "2")

    def test_incomplete_contributors_vote_form(self):
        """
        Submits a student vote, verifies that an error message is displayed if not all rating questions about
        contributors have been answered and that all given answers stay selected/filled.
        """
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_contributors_complete=False)
        response = form.submit(status=200)
        self.assertIn("vote for all rating questions", response)
        self.assertIn("skip the questions about a single person", response)

        form = page.forms["student-vote-form"]

        field_id = partial(answer_field_id, self.evaluation.general_contribution, self.top_general_questionnaire)
        self.assertEqual(form[field_id(self.top_text_question)].value, "some text")
        self.assertEqual(form[field_id(self.top_likert_question)].value, "1")
        self.assertEqual(
            form[field_id(self.top_likert_question, additional_textanswer=True)].value, "some additional text"
        )
        self.assertEqual(form[field_id(self.top_grade_question)].value, "3")

        field_id = partial(answer_field_id, self.evaluation.general_contribution, self.bottom_general_questionnaire)
        self.assertEqual(form[field_id(self.bottom_text_question)].value, "some bottom text")
        self.assertEqual(form[field_id(self.bottom_likert_question)].value, "2")
        self.assertEqual(form[field_id(self.bottom_grade_question)].value, "4")

        field_id = partial(answer_field_id, self.contribution1, self.contributor_questionnaire)
        self.assertEqual(form[field_id(self.contributor_text_question)].value, "some other text")
        self.assertEqual(form[field_id(self.contributor_likert_question)].value, "4")
        self.assertEqual(
            form[field_id(self.contributor_likert_question, additional_textanswer=True)].value,
            "some other additional text",
        )

        field_id = partial(answer_field_id, self.contribution2, self.contributor_questionnaire)
        self.assertEqual(form[field_id(self.contributor_text_question)].value, "some more text")

    def test_answer(self):
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())

        page = self.app.get(self.url, user=self.voting_user2, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())

        self.assertEqual(len(TextAnswer.objects.all()), 12)
        self.assertEqual(len(RatingAnswerCounter.objects.all()), 6)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.top_likert_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.top_likert_question).answer, 1)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.top_grade_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.top_grade_question).answer, 3)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.bottom_likert_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.bottom_likert_question).answer, 2)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.bottom_grade_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.bottom_grade_question).answer, 4)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question).count(), 2)
        self.assertEqual(
            RatingAnswerCounter.objects.get(
                question=self.contributor_likert_question, contribution=self.contribution1
            ).answer,
            4,
        )
        self.assertEqual(
            RatingAnswerCounter.objects.get(
                question=self.contributor_likert_question, contribution=self.contribution2
            ).answer,
            2,
        )

        self.assertEqual(TextAnswer.objects.filter(question=self.top_text_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.top_likert_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.bottom_text_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question).count(), 4)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_likert_question).count(), 2)

        self.assertEqual(
            TextAnswer.objects.filter(question=self.top_text_question)[0].contribution,
            self.evaluation.general_contribution,
        )
        self.assertEqual(
            TextAnswer.objects.filter(question=self.top_text_question)[1].contribution,
            self.evaluation.general_contribution,
        )

        answers = TextAnswer.objects.filter(
            question=self.contributor_text_question, contribution=self.contribution1
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some other text"] * 2)

        answers = TextAnswer.objects.filter(
            question=self.contributor_likert_question, contribution=self.contribution1
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some other additional text"] * 2)

        answers = TextAnswer.objects.filter(
            question=self.contributor_text_question, contribution=self.contribution2
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some more text"] * 2)

        answers = TextAnswer.objects.filter(
            question=self.top_text_question, contribution=self.evaluation.general_contribution
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some text"] * 2)

        answers = TextAnswer.objects.filter(
            question=self.top_likert_question, contribution=self.evaluation.general_contribution
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some additional text"] * 2)

        answers = TextAnswer.objects.filter(
            question=self.bottom_text_question, contribution=self.evaluation.general_contribution
        ).values_list("answer", flat=True)
        self.assertEqual(list(answers), ["some bottom text"] * 2)

    def test_vote_timestamp(self):
        time_before = datetime.datetime.now()
        timestamps_before = VoteTimestamp.objects.count()
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        form.submit()
        self.assertEqual(VoteTimestamp.objects.count(), timestamps_before + 1)
        time = VoteTimestamp.objects.latest("timestamp").timestamp
        self.assertTrue(time_before < time < datetime.datetime.now())

    def test_user_cannot_vote_multiple_times(self):
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        form.submit()

        self.app.get(self.url, user=self.voting_user1, status=403)

    def test_user_cannot_vote_for_themselves(self):
        response = self.app.get(self.url, user=self.contributor1, status=200)

        for contributor, __, __, __, __ in response.context["contributor_form_groups"]:
            self.assertNotEqual(
                contributor, self.contributor1, "Contributor should not see the questionnaire about themselves"
            )

        response = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertTrue(
            any(
                contributor == self.contributor1
                for contributor, __, __, __, __ in response.context["contributor_form_groups"]
            ),
            "Regular students should see the questionnaire about a contributor",
        )

    def test_user_logged_out(self):
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)

        page = page.forms["logout-form"].submit(status=302)

        response = form.submit(status=302)
        self.assertNotIn(SUCCESS_MAGIC_STRING, response)

    def test_midterm_evaluation_warning(self):
        evaluation_warning = "The results of this evaluation will be published while the course is still running."
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertNotIn(evaluation_warning, page)

        self.evaluation.is_midterm_evaluation = True
        self.evaluation.save()

        page = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertIn(evaluation_warning, page)

    @override_settings(SMALL_COURSE_SIZE=5)
    def test_small_evaluation_size_warning_shown(self):
        small_evaluation_size_warning = "Only a small number of people can take part in this evaluation."
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertIn(small_evaluation_size_warning, page)

    @override_settings(SMALL_COURSE_SIZE=2)
    def test_small_evaluation_size_warning_not_shown(self):
        small_evaluation_size_warning = "Only a small number of people can take part in this evaluation."
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertNotIn(small_evaluation_size_warning, page)

    def helper_test_answer_publish_confirmation(self, form_element):
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        if form_element:
            form[form_element] = True
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())
        evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        if form_element:
            self.assertTrue(evaluation.can_publish_text_results)
        else:
            self.assertFalse(evaluation.can_publish_text_results)

    def test_user_checked_top_textanswer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation("text_results_publish_confirmation_top")

    def test_user_checked_bottom_textanswer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation("text_results_publish_confirmation_bottom")

    def test_user_did_not_check_textanswer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation(None)

    def test_textanswer_visibility_is_shown(self):
        page = self.app.get(self.url, user=self.voting_user1, status=200)
        self.assertRegex(
            page.body.decode(),
            r"can be seen by:<br />\s*{}".format(self.contributor1.full_name.replace("(", "\\(").replace(")", "\\)")),
        )

    def test_xmin_of_all_answers_is_updated(self):
        page = self.app.get(self.url, user=self.voting_user1)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        form.submit()

        page = self.app.get(self.url, user=self.voting_user2)
        form = page.forms["student-vote-form"]
        self.fill_form(form)
        form[
            answer_field_id(
                self.evaluation.general_contribution, self.top_general_questionnaire, self.top_grade_question
            )
        ] = 2
        form.submit()

        self.assertEqual(
            set(Answer.__subclasses__()),
            {RatingAnswerCounter, TextAnswer},
            "This test requires an update if a new answer type is added. Also, when adding a new answer type, "
            "the new table should probably also be vacuumed and clustered -- see and update "
            "https://github.com/e-valuation/EvaP/wiki/Installation#database-vacuuming-and-clustering",
        )

        query = RatingAnswerCounter.objects.raw("SELECT id, xmin FROM evaluation_ratinganswercounter")
        rating_answer_xmins = [row.xmin for row in query]
        self.assertTrue(all(xmin == rating_answer_xmins[0] for xmin in rating_answer_xmins))

        query = TextAnswer.objects.raw("SELECT id, xmin FROM evaluation_textanswer")
        text_answer_xmins = [row.xmin for row in query]
        self.assertTrue(all(xmin == text_answer_xmins[0] for xmin in text_answer_xmins))
