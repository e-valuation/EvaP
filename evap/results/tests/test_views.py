from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from model_bakery import baker

from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    Evaluation,
    Program,
    Question,
    Questionnaire,
    QuestionType,
    RatingAnswerCounter,
    Semester,
    UserProfile,
)
from evap.evaluation.tests.tools import (
    TestCase,
    WebTest,
    let_user_vote_for_evaluation,
    make_manager,
    make_rating_answer_counters,
    render_pages,
)
from evap.results.exporters import TextAnswerExporter
from evap.results.tools import cache_results
from evap.results.views import get_evaluations_with_prefetched_data, update_template_cache
from evap.staff.tests.utils import WebTestStaffMode, helper_exit_staff_mode, run_in_staff_mode


class TestResultsView(WebTest):
    url = "/results/"

    @render_pages
    def render_pages(self):
        def make_winter_semester(year):
            return baker.make(
                Semester,
                name_de=f"Wintersemester {year}/{year + 1}",
                name_en=f"Winter term {year}/{year + 1}",
                short_name_de=f"WS {year % 1000}/{year % 1000 + 1}",
                short_name_en=f"WT {year % 1000}/{year % 1000 + 1}",
            )

        def make_summer_semester(year):
            return baker.make(
                Semester,
                name_de=f"Sommersemester {year}",
                name_en=f"Summer term {year}",
                short_name_de=f"SS {year % 1000}",
                short_name_en=f"ST {year % 1000}",
            )

        semesters = [
            make_summer_semester(2014),
            make_winter_semester(2013),
            make_summer_semester(2013),
        ]
        programs = {
            "ba-a": baker.make(Program, name_de="Bachelor A", name_en="Bachelor A"),
            "ma-a": baker.make(Program, name_de="Master A", name_en="Master A"),
            "ma-b": baker.make(Program, name_de="Master B", name_en="Master B"),
        }
        course_types = {
            "l": baker.make(CourseType, name_de="Vorlesung", name_en="Lecture"),
            "s": baker.make(CourseType, name_de="Seminar", name_en="Seminar"),
        }

        def make_responsible(title, first_name, last_name):
            return baker.make(
                UserProfile,
                title=title,
                first_name_given=first_name,
                last_name=last_name,
            )

        responsibles = {
            "responsible": make_responsible("Prof. Dr.", "", "responsible"),
            "goldwasser": make_responsible("Dr.", "Clara", "Goldwasser"),
            "kuchenbuch": make_responsible("Dr.", "Tony", "Kuchenbuch"),
        }

        def make_course(name, semester, course_type_name, program_names, responsible_names):
            return baker.make(
                Course,
                semester=semesters[semester],
                name_de=f"Veranstaltung {name}",
                name_en=f"Course {name}",
                type=course_types[course_type_name],
                programs={programs[program_name] for program_name in program_names},
                responsibles={responsibles[responsible_name] for responsible_name in responsible_names},
            )

        courses = {
            "a-0": make_course("A", 0, "l", {"ba-a"}, {"responsible"}),
            "a-1": make_course("A", 1, "l", {"ba-a"}, {"responsible"}),
            "a-2": make_course("A", 2, "l", {"ba-a"}, {"responsible"}),
            "c": make_course("C", 0, "s", {"ba-a", "ma-a"}, {"goldwasser"}),
            "d": make_course("D", 0, "l", {"ma-a", "ma-b"}, {"kuchenbuch", "goldwasser"}),
            "e": make_course("E", 2, "s", {"ma-a"}, {"kuchenbuch"}),
        }

        def make_evaluation(course_name, participant_count, voter_count, **attrs):
            baker.make(
                Evaluation,
                state=Evaluation.State.PUBLISHED,
                course=courses[course_name],
                _participant_count=participant_count,
                _voter_count=voter_count,
                **attrs,
            )

        make_evaluation("a-0", 100, 80)
        make_evaluation("a-1", 100, 85)
        make_evaluation("a-2", 100, 80)
        make_evaluation("a-2", 100, 75, name_de="Klausur", name_en="Exam")
        make_evaluation("c", 20, 15)
        make_evaluation("d", 50, 45)
        make_evaluation("e", 5, 5)

        return {
            "student": self.app.get(self.url, user="student@institution.example.com").content,
        }

    @patch("evap.evaluation.models.Evaluation.can_be_seen_by", new=(lambda self, user: True))
    def test_multiple_evaluations_per_course(self):
        student = baker.make(UserProfile, email="student@institution.example.com")

        # course with no evaluations does not show up
        course = baker.make(Course)
        page = self.app.get(self.url, user=student)
        self.assertNotContains(page, course.name)
        caches["results"].clear()

        # course with one evaluation is a single line with the evaluation's full_name
        evaluation = baker.make(
            Evaluation,
            course=course,
            name_en="unique_evaluation_name1",
            name_de="foo",
            state=Evaluation.State.PUBLISHED,
        )
        page = self.app.get(self.url, user=student)
        self.assertContains(page, evaluation.full_name)
        caches["results"].clear()

        # course with two evaluations is three lines without using the full names
        evaluation2 = baker.make(
            Evaluation,
            course=course,
            name_en="unique_evaluation_name2",
            name_de="bar",
            state=Evaluation.State.PUBLISHED,
        )
        page = self.app.get(self.url, user=student)
        self.assertContains(page, course.name)
        self.assertContains(page, evaluation.name_en)
        self.assertContains(page, evaluation2.name_en)
        self.assertNotContains(page, evaluation.full_name)
        self.assertNotContains(page, evaluation2.full_name)
        caches["results"].clear()

    @patch("evap.evaluation.models.Evaluation.can_be_seen_by", new=(lambda self, user: True))
    def test_order(self):
        student = baker.make(UserProfile, email="student@institution.example.com", language="de")

        course = baker.make(Course)
        evaluation1 = baker.make(
            Evaluation,
            name_de="random_evaluation_d",
            name_en="random_evaluation_a",
            course=course,
            state=Evaluation.State.PUBLISHED,
        )
        evaluation2 = baker.make(
            Evaluation,
            name_de="random_evaluation_c",
            name_en="random_evaluation_b",
            course=course,
            state=Evaluation.State.PUBLISHED,
        )

        page = self.app.get(self.url, user=student).body.decode()
        self.assertGreater(page.index(evaluation1.name_de), page.index(evaluation2.name_de))

        student.language = "en"
        student.save()
        page = self.app.get(self.url, user=student).body.decode()
        self.assertLess(page.index(evaluation1.name_en), page.index(evaluation2.name_en))

    # using LocMemCache so the cache queries don't show up in the query count that's measured here
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "testing_cache_default",
            },
            "sessions": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "testing_cache_results",
            },
            "results": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "testing_cache_sessions",
            },
        }
    )
    @patch("evap.evaluation.models.Evaluation.can_be_seen_by", new=(lambda self, user: True))
    def test_num_queries_is_constant(self):
        """
        ensures that the number of queries in the user list is constant
        and not linear to the number of courses/evaluations
        """
        student = baker.make(UserProfile, email="student@institution.example.com")

        # warm up some caches
        self.app.get(self.url, user=student)

        def make_course_with_evaluations(unique_suffix):
            course = baker.make(Course)
            baker.make(
                Evaluation,
                course=course,
                name_en="foo" + unique_suffix,
                name_de="foo" + unique_suffix,
                state=Evaluation.State.PUBLISHED,
                _voter_count=0,
                _participant_count=0,
            )
            baker.make(
                Evaluation,
                course=course,
                name_en="bar" + unique_suffix,
                name_de="bar" + unique_suffix,
                state=Evaluation.State.PUBLISHED,
                _voter_count=0,
                _participant_count=0,
            )

        # first measure the number of queries with two courses
        make_course_with_evaluations("frob")
        make_course_with_evaluations("spam")
        call_command("refresh_results_cache", stdout=StringIO())
        with CaptureQueriesContext(connection) as context:
            self.app.get(self.url, user=student)
        num_queries_before = context.final_queries - context.initial_queries

        # then measure the number of queries with one more course and compare
        make_course_with_evaluations("eggs")
        call_command("refresh_results_cache", stdout=StringIO())
        with CaptureQueriesContext(connection) as context:
            self.app.get(self.url, user=student)
        num_queries_after = context.final_queries - context.initial_queries

        self.assertEqual(num_queries_before, num_queries_after)

        # django does not clear the LocMemCache in between tests. clear it here just to be safe.
        caches["default"].clear()
        caches["sessions"].clear()
        caches["results"].clear()

    def test_evaluation_weight_sums(self):
        """Regression test for #1691"""
        student = baker.make(UserProfile, email="student@institution.example.com")
        course = baker.make(Course)

        published = baker.make(
            Evaluation,
            course=course,
            name_en=iter(["evaluation_1", "evaluation_2", "evaluation_3"]),
            state=iter([Evaluation.State.NEW, Evaluation.State.PUBLISHED, Evaluation.State.PUBLISHED]),
            weight=iter([8, 3, 4]),
            is_single_result=True,
            _quantity=3,
            _fill_optional=["name_de"],
        )[1:]

        contributions = [e.general_contribution for e in published]
        baker.make(RatingAnswerCounter, contribution=iter(contributions), answer=2, count=2, _quantity=len(published))
        update_template_cache(published)

        page = self.app.get(self.url, user=student)
        decoded = page.body.decode()

        self.assertTrue(
            decoded.index("evaluation_2")
            < decoded.index("contributes 20% to")
            < decoded.index("evaluation_3")
            < decoded.index("contributes 26% to")
        )
        self.assertNotContains(page, "contributes 53% to")


class TestGetEvaluationsWithPrefetchedData(TestCase):
    def test_returns_correct_participant_count(self):
        """Regression test for #1248"""
        participants = baker.make(UserProfile, _bulk_create=True, _quantity=2)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
            participants=participants,
            voters=participants,
        )
        cache_results(evaluation)
        participants[0].delete()
        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        evaluations = get_evaluations_with_prefetched_data([evaluation])
        self.assertEqual(evaluations[0].num_participants, 2)
        self.assertEqual(evaluations[0].num_voters, 2)
        evaluations = get_evaluations_with_prefetched_data(Evaluation.objects.filter(pk=evaluation.pk))
        self.assertEqual(evaluations[0].num_participants, 2)
        self.assertEqual(evaluations[0].num_voters, 2)


class TestResultsViewContributionWarning(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        contributor = baker.make(UserProfile)

        # Set up an evaluation with one question but no answers
        students = list(baker.make(UserProfile, _quantity=2, _bulk_create=True))
        cls.evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course=baker.make(Course, semester=cls.semester),
            participants=students,
            voters=students,
        )
        cls.questionnaire = baker.make(Questionnaire)
        cls.evaluation.general_contribution.questionnaires.set([cls.questionnaire])
        cls.contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
            contributor=contributor,
        )
        cls.likert_question = baker.make(
            Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=cls.questionnaire, order=2
        )
        cls.url = f"/results/semester/{cls.semester.id}/evaluation/{cls.evaluation.id}"

    def test_contributor_no_results_warning(self):
        # The contributor card should be collapsed iff all questions have no results
        # Regression test from https://github.com/e-valuation/EvaP/pull/2245
        question2 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=self.questionnaire, order=2)

        cache_results(self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertIn("There are no results for this person", page)
        self.assertIn('class="collapse"', page)

        make_rating_answer_counters(question2, self.contribution, [0, 0, 10, 0, 0])

        cache_results(self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertNotIn("There are no results for this person", page)
        self.assertNotIn('class="collapse"', page)

    def test_many_answers_evaluation_no_warning(self):
        make_rating_answer_counters(self.likert_question, self.contribution, [0, 0, 10, 0, 0])
        cache_results(self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_zero_answers_evaluation_no_warning(self):
        cache_results(self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_few_answers_evaluation_show_warning(self):
        make_rating_answer_counters(self.likert_question, self.contribution, [0, 0, 3, 0, 0])
        cache_results(self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertIn("Only a few participants answered these questions.", page)


class TestResultsSemesterEvaluationDetailView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)

        contributor = baker.make(UserProfile, email="contributor@institution.example.com")
        responsible = baker.make(UserProfile, email="responsible@institution.example.com")

        cls.test_users = [cls.manager, contributor, responsible]

        # Normal evaluation with responsible and contributor.
        cls.evaluation = baker.make(
            Evaluation, state=Evaluation.State.PUBLISHED, course=baker.make(Course, semester=cls.semester)
        )

        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=responsible,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=contributor,
            role=Contribution.Role.EDITOR,
        )

        cls.url = f"/results/semester/{cls.semester.id}/evaluation/{cls.evaluation.id}"

    def test_questionnaire_ordering(self):
        top_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        bottom_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM)

        top_heading_question = baker.make(Question, type=QuestionType.HEADING, questionnaire=top_questionnaire, order=0)
        top_likert_question = baker.make(
            Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=top_questionnaire, order=1
        )

        contributor_likert_question = baker.make(
            Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=contributor_questionnaire
        )

        bottom_heading_question = baker.make(
            Question, type=QuestionType.HEADING, questionnaire=bottom_questionnaire, order=0
        )
        bottom_likert_question = baker.make(
            Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=bottom_questionnaire, order=1
        )

        self.evaluation.general_contribution.questionnaires.set([top_questionnaire, bottom_questionnaire])
        self.contribution.questionnaires.set([contributor_questionnaire])

        make_rating_answer_counters(top_likert_question, self.evaluation.general_contribution)
        make_rating_answer_counters(contributor_likert_question, self.contribution)
        make_rating_answer_counters(bottom_likert_question, self.evaluation.general_contribution)

        cache_results(self.evaluation)

        content = self.app.get(self.url, user=self.manager).body.decode()

        top_heading_index = content.index(top_heading_question.text)
        top_likert_index = content.index(top_likert_question.text)
        contributor_likert_index = content.index(contributor_likert_question.text)
        bottom_heading_index = content.index(bottom_heading_question.text)
        bottom_likert_index = content.index(bottom_likert_question.text)

        self.assertTrue(
            top_heading_index < top_likert_index < contributor_likert_index < bottom_heading_index < bottom_likert_index
        )

    def test_heading_question_filtering(self):
        contributor = baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire)

        heading_question_0 = baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=0)
        heading_question_1 = baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=1)
        likert_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire, order=2)
        heading_question_2 = baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=3)

        contribution = baker.make(
            Contribution, evaluation=self.evaluation, questionnaires=[questionnaire], contributor=contributor
        )
        make_rating_answer_counters(likert_question, contribution)

        cache_results(self.evaluation)

        page = self.app.get(self.url, user=self.manager)

        self.assertNotIn(heading_question_0.text, page)
        self.assertIn(heading_question_1.text, page)
        self.assertIn(likert_question.text, page)
        self.assertNotIn(heading_question_2.text, page)

    @override_settings(VOTER_COUNT_NEEDED_FOR_PUBLISHING_RATING_RESULTS=0)
    def test_default_view_is_public(self):
        cache_results(self.evaluation)

        page_without_get_parameter = self.app.get(self.url, user=self.manager)
        self.assertEqual(page_without_get_parameter.context["view"], "public")

        page_with_get_parameter = self.app.get(self.url + "?view=public", user=self.manager)
        self.assertEqual(page_with_get_parameter.context["view"], "public")

        page_with_random_get_parameter = self.app.get(self.url + "?view=asdf", user=self.manager)
        self.assertEqual(page_with_random_get_parameter.context["view"], "public")

        page_with_full_get_parameter = self.app.get(f"{self.url}?view=full", user=self.manager)
        self.assertEqual(page_with_full_get_parameter.context["view"], "full")

        page_with_export_get_parameter = self.app.get(f"{self.url}?view=export", user=self.manager)
        self.assertEqual(page_with_export_get_parameter.context["view"], "export")

    def test_wrong_state(self):
        helper_exit_staff_mode(self)
        evaluation = baker.make(
            Evaluation, state=Evaluation.State.REVIEWED, course=baker.make(Course, semester=self.semester)
        )
        cache_results(evaluation)
        url = f"/results/semester/{self.semester.id}/evaluation/{evaluation.id}"
        self.app.get(url, user="student@institution.example.com", status=403)

    def test_preview_without_rating_answers(self):
        evaluation = baker.make(
            Evaluation, state=Evaluation.State.EVALUATED, course=baker.make(Course, semester=self.semester)
        )
        cache_results(evaluation)
        url = f"/results/semester/{self.semester.id}/evaluation/{evaluation.id}"
        self.app.get(url, user=self.manager)

    def test_preview_with_rating_answers(self):
        evaluation = baker.make(
            Evaluation, state=Evaluation.State.EVALUATED, course=baker.make(Course, semester=self.semester)
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        likert_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire, order=1)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        participants = baker.make(UserProfile, _bulk_create=True, _quantity=20)
        evaluation.participants.set(participants)
        evaluation.voters.set(participants)
        make_rating_answer_counters(likert_question, evaluation.general_contribution, [20, 0, 0, 0, 0])
        cache_results(evaluation)

        url = f"/results/semester/{self.semester.id}/evaluation/{evaluation.id}"
        self.app.get(url, user=self.manager)

    def test_unpublished_single_results_show_results(self) -> None:
        """Regression test for #1621"""
        # make regular evaluation with some answers
        participants = baker.make(UserProfile, _bulk_create=True, _quantity=20)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            course=baker.make(Course, semester=self.semester),
            participants=participants,
            voters=participants,
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        likert_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire, order=1)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        make_rating_answer_counters(likert_question, evaluation.general_contribution)

        # make single result
        evaluation2: Evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            course=evaluation.course,
            is_single_result=True,
            name_de="foo",
            name_en="foo",
            participants=participants,
            voters=participants,
        )
        evaluation2.general_contribution.questionnaires.set([questionnaire])
        make_rating_answer_counters(likert_question, evaluation2.general_contribution)

        cache_results(evaluation)

        url = f"/results/semester/{self.semester.id}/evaluation/{evaluation.id}"
        response = self.app.get(url, user=self.manager)

        # this one is the course result. The two evaluations shouldn't use this
        self.assertTemplateUsed(response, "distribution_with_grade_disabled.html", count=1)
        # Both evaluations should use this
        self.assertTemplateUsed(response, "evaluation_result_widget.html", count=2)
        # Both evaluations should use this, plus one for the questionnaire
        self.assertTemplateUsed(response, "distribution_with_grade.html", count=3)

    def test_invalid_contributor_id(self):
        cache_results(self.evaluation)
        self.app.get(self.url + "?contributor_id=", user=self.manager, status=400)
        self.app.get(self.url + "?contributor_id=asd", user=self.manager, status=400)
        self.app.get(self.url + "?contributor_id=1234", user=self.manager, status=404)

    def test_evaluation_sorting(self):
        names = ["EvaluationB", "EvaluationA", "EvaluationC"]
        additional_evaluations = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course=self.evaluation.course,
            _quantity=3,
            _bulk_create=True,
            name_en=iter(names),
            name_de=iter(names),
        )

        for evaluation in (self.evaluation, *additional_evaluations):
            cache_results(evaluation)

        body = self.app.get(self.url, user=self.manager).body.decode()
        self.assertTrue(body.find("EvaluationA") < body.find("EvaluationB") < body.find("EvaluationC"))


class TestResultsSemesterEvaluationDetailViewFewVoters(WebTest):
    @classmethod
    def setUpTestData(cls):
        make_manager()
        responsible = baker.make(UserProfile, email="responsible@institution.example.com")
        cls.student1 = baker.make(UserProfile, email="student1@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")
        students = baker.make(UserProfile, _bulk_create=True, _quantity=10)
        students.extend([cls.student1, cls.student2])

        cls.evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION, participants=students)
        cls.url = f"/results/semester/{cls.evaluation.course.semester.pk}/evaluation/{cls.evaluation.pk}"

        questionnaire = baker.make(Questionnaire)
        cls.question_grade = baker.make(Question, questionnaire=questionnaire, type=QuestionType.GRADE)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])
        cls.responsible_contribution = baker.make(
            Contribution, contributor=responsible, evaluation=cls.evaluation, questionnaires=[questionnaire]
        )

    def helper_test_answer_visibility_one_voter(self, user_email, expect_page_not_visible=False):
        page = self.app.get(self.url, user=user_email, expect_errors=expect_page_not_visible)
        if expect_page_not_visible:
            self.assertEqual(page.status_code, 403)
        else:
            self.assertEqual(page.status_code, 200)
            number_of_grade_badges = str(page).count("badge-grade")
            self.assertEqual(number_of_grade_badges, 5)  # 1 evaluation overview and 4 questions
            number_of_visible_grade_badges = str(page).count("background-color")
            self.assertEqual(number_of_visible_grade_badges, 0)
            number_of_disabled_grade_badges = str(page).count("badge-grade badge-disabled")
            self.assertEqual(number_of_disabled_grade_badges, 5)

    def helper_test_answer_visibility_two_voters(self, user_email):
        page = self.app.get(self.url, user=user_email)
        number_of_grade_badges = str(page).count("badge-grade")
        self.assertEqual(number_of_grade_badges, 5)  # 1 evaluation overview and 4 questions
        number_of_visible_grade_badges = str(page).count("background-color")
        self.assertEqual(number_of_visible_grade_badges, 4)  # all but average grade in evaluation overview
        number_of_disabled_grade_badges = str(page).count("badge-grade badge-disabled")
        self.assertEqual(number_of_disabled_grade_badges, 1)

    def test_answer_visibility_one_voter(self):
        let_user_vote_for_evaluation(self.student1, self.evaluation)
        self.evaluation.end_evaluation()
        self.evaluation.end_review()
        self.evaluation.publish()
        self.evaluation.save()
        self.assertEqual(self.evaluation.voters.count(), 1)
        with run_in_staff_mode(self):
            self.helper_test_answer_visibility_one_voter("manager@institution.example.com")
        self.evaluation = Evaluation.objects.get(id=self.evaluation.id)
        self.helper_test_answer_visibility_one_voter("responsible@institution.example.com")
        self.helper_test_answer_visibility_one_voter("student@institution.example.com", expect_page_not_visible=True)

    def test_answer_visibility_two_voters(self):
        let_user_vote_for_evaluation(self.student1, self.evaluation, create_answers=True)
        let_user_vote_for_evaluation(self.student2, self.evaluation, create_answers=True)
        self.evaluation.end_evaluation()
        self.evaluation.end_review()
        self.evaluation.publish()
        self.evaluation.save()
        self.assertEqual(self.evaluation.voters.count(), 2)

        with run_in_staff_mode(self):
            self.helper_test_answer_visibility_two_voters("manager@institution.example.com")
        self.helper_test_answer_visibility_two_voters("responsible@institution.example.com")
        self.helper_test_answer_visibility_two_voters("student@institution.example.com")


class TestResultsSemesterEvaluationDetailViewPrivateEvaluation(WebTest):
    @patch("evap.results.templatetags.results_templatetags.get_grade_color", new=lambda x: (0, 0, 0))
    def test_private_evaluation(self):
        semester = baker.make(Semester)
        manager = make_manager()
        student = baker.make(UserProfile, email="student@institution.example.com")
        student_external = baker.make(UserProfile, email="student_external@example.com")
        contributor = baker.make(UserProfile, email="contributor@institution.example.com")
        responsible = baker.make(UserProfile, email="responsible@institution.example.com")
        editor = baker.make(UserProfile, email="editor@institution.example.com")
        voter1 = baker.make(UserProfile, email="voter1@institution.example.com")
        voter2 = baker.make(UserProfile, email="voter2@institution.example.com")
        non_participant = baker.make(UserProfile, email="non_participant@institution.example.com")
        program = baker.make(Program)
        course = baker.make(
            Course, semester=semester, programs=[program], is_private=True, responsibles=[responsible, editor]
        )
        private_evaluation = baker.make(
            Evaluation,
            course=course,
            state=Evaluation.State.PUBLISHED,
            participants=[student, student_external, voter1, voter2],
            voters=[voter1, voter2],
        )
        private_evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])
        baker.make(
            Contribution,
            evaluation=private_evaluation,
            contributor=editor,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(Contribution, evaluation=private_evaluation, contributor=contributor, role=Contribution.Role.EDITOR)
        cache_results(private_evaluation)

        url = "/results/"
        self.assertNotIn(private_evaluation.full_name, self.app.get(url, user=non_participant))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user=student))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user=responsible))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user=editor))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user=contributor))
        with run_in_staff_mode(self):
            self.assertIn(private_evaluation.full_name, self.app.get(url, user=manager))
        self.app.get(url, user=student_external, status=403)  # external users can't see results semester view

        url = f"/results/semester/{semester.id}/evaluation/{private_evaluation.id}"
        self.app.get(url, user=non_participant, status=403)
        self.app.get(url, user=student, status=200)
        self.app.get(url, user=responsible, status=200)
        self.app.get(url, user=editor, status=200)
        self.app.get(url, user=contributor, status=200)
        with run_in_staff_mode(self):
            self.app.get(url, user=manager, status=200)

        # this external user participates in the evaluation and can see the results
        self.app.get(url, user=student_external, status=200)


class TestResultsTextanswerVisibilityForManager(WebTestStaffMode):
    fixtures = ["minimal_test_data_results"]

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cache_results(Evaluation.objects.get(id=1))

    def test_textanswer_visibility_for_manager_before_publish(self):
        evaluation = Evaluation.objects.get(id=1)
        voter_count = evaluation._voter_count
        participant_count = evaluation._participant_count
        evaluation._voter_count = 0  # set these to 0 to make unpublishing work
        evaluation._participant_count = 0
        evaluation.unpublish()
        evaluation._voter_count = voter_count  # reset to original values
        evaluation._participant_count = participant_count
        evaluation.save()

        page = self.app.get("/results/semester/1/evaluation/1?view=full", user=self.manager)
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_manager(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=full", user=self.manager)
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)


class TestResultsTextanswerVisibility(WebTest):
    fixtures = ["minimal_test_data_results"]

    @classmethod
    def setUpTestData(cls):
        cache_results(Evaluation.objects.get(id=1))

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible@institution.example.com")
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_responsible_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible_contributor@institution.example.com")
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_delegate_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="delegate_for_responsible@institution.example.com")
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="contributor@institution.example.com")
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_delegate_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="delegate_for_contributor@institution.example.com")
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_contributor_general_textanswers(self):
        page = self.app.get(
            "/results/semester/1/evaluation/1", user="contributor_general_textanswers@institution.example.com"
        )
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="student@institution.example.com")
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_additional_orig_published.", page)
        self.assertNotIn(".general_additional_orig_hidden.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_published.", page)
        self.assertNotIn(".responsible_contributor_additional_orig_hidden.", page)

    def test_textanswer_visibility_for_student_external(self):
        # the external user does not participate in or contribute to the evaluation and therefore can't see the results
        self.app.get("/results/semester/1/evaluation/1", user="student_external@example.com", status=403)

    def test_textanswer_visibility_info_is_shown(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="contributor@institution.example.com")
        self.assertRegex(page.body.decode(), r"can be seen by:<br />\s*contributor user")

    def test_textanswer_visibility_info_for_proxy_user(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible@institution.example.com")
        self.assertIn("responsible_contributor user (1 person)", page)


class TestResultsOtherContributorsListOnExportView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.responsible = baker.make(UserProfile, email="responsible@institution.example.com")

        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED)
        cls.url = f"/results/semester/{evaluation.course.semester.id}/evaluation/{evaluation.id}?view=export"

        questionnaire = baker.make(Questionnaire)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.POSITIVE_LIKERT)
        evaluation.general_contribution.questionnaires.set([questionnaire])

        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=cls.responsible,
            questionnaires=[questionnaire],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.other_contributor_1 = baker.make(UserProfile, email="other_contributor_1@institution.example.com")
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=cls.other_contributor_1,
            questionnaires=[questionnaire],
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        cls.other_contributor_2 = baker.make(UserProfile, email="other_contributor_2@institution.example.com")
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=cls.other_contributor_2,
            questionnaires=[questionnaire],
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        cache_results(evaluation)

    def test_contributor_list(self):
        page = self.app.get(self.url, user=self.responsible)
        self.assertIn(f"<li>{self.other_contributor_1.full_name}</li>", page)
        self.assertIn(f"<li>{self.other_contributor_2.full_name}</li>", page)


class TestResultsTextanswerVisibilityForExportView(WebTest):
    fixtures = ["minimal_test_data_results"]

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cache_results(Evaluation.objects.get(id=1))

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="responsible@institution.example.com")

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_responsible_contributor(self):
        page = self.app.get(
            "/results/semester/1/evaluation/1?view=export", user="responsible_contributor@institution.example.com"
        )

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="contributor@institution.example.com")

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor_general_textanswers(self):
        page = self.app.get(
            "/results/semester/1/evaluation/1?view=export",
            user="contributor_general_textanswers@institution.example.com",
        )

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="student@institution.example.com")

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_manager(self):
        with run_in_staff_mode(self):
            contributor_id = UserProfile.objects.get(email="responsible@institution.example.com").id
            page = self.app.get(
                f"/results/semester/1/evaluation/1?view=export&contributor_id={contributor_id}",
                user="manager@institution.example.com",
            )

            self.assertIn(".general_orig_published.", page)
            self.assertNotIn(".general_orig_hidden.", page)
            self.assertNotIn(".general_orig_published_changed.", page)
            self.assertIn(".general_changed_published.", page)
            self.assertNotIn(".contributor_orig_published.", page)
            self.assertNotIn(".contributor_orig_private.", page)
            self.assertNotIn(".responsible_contributor_orig_published.", page)
            self.assertNotIn(".responsible_contributor_orig_hidden.", page)
            self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
            self.assertNotIn(".responsible_contributor_changed_published.", page)
            self.assertNotIn(".responsible_contributor_orig_private.", page)
            self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_manager_contributor(self):
        manager_group = Group.objects.get(name="Manager")
        contributor = UserProfile.objects.get(email="contributor@institution.example.com")
        contributor.groups.add(manager_group)
        page = self.app.get(
            f"/results/semester/1/evaluation/1?view=export&contributor_id={contributor.id}",
            user="contributor@institution.example.com",
        )

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)


class TestArchivedResults(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)
        cls.manager = make_manager()
        cls.reviewer = baker.make(
            UserProfile, email="reviewer@institution.example.com", groups=[Group.objects.get(name="Reviewer")]
        )
        cls.student = baker.make(UserProfile, email="student@institution.example.com")
        cls.student_external = baker.make(UserProfile, email="student_external@example.com")
        cls.contributor = baker.make(UserProfile, email="contributor@institution.example.com")
        cls.responsible = baker.make(UserProfile, email="responsible@institution.example.com")

        course = baker.make(
            Course, semester=cls.semester, programs=[baker.make(Program)], responsibles=[cls.responsible]
        )
        cls.evaluation = baker.make(
            Evaluation,
            course=course,
            state=Evaluation.State.PUBLISHED,
            participants=[cls.student, cls.student_external],
            voters=[cls.student, cls.student_external],
        )
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=cls.responsible,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(Contribution, evaluation=cls.evaluation, contributor=cls.contributor)
        cache_results(cls.evaluation)

    @patch("evap.results.templatetags.results_templatetags.get_grade_color", new=lambda x: (0, 0, 0))
    def test_unarchived_results(self):
        url = "/results/"
        self.assertIn(self.evaluation.full_name, self.app.get(url, user=self.student))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user=self.responsible))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user=self.contributor))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user=self.manager))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user=self.reviewer))
        self.app.get(url, user=self.student_external, status=403)  # external users can't see results semester view

        url = f"/results/semester/{self.semester.id}/evaluation/{self.evaluation.id}"
        self.app.get(url, user=self.student, status=200)
        self.app.get(url, user=self.responsible, status=200)
        self.app.get(url, user=self.contributor, status=200)
        self.app.get(url, user=self.manager, status=200)
        self.app.get(url, user=self.reviewer, status=200)
        self.app.get(url, user=self.student_external, status=200)

    def test_archived_results(self):
        self.semester.archive_results()

        url = f"/results/semester/{self.semester.id}/evaluation/{self.evaluation.id}"
        self.app.get(url, user=self.student, status=403)
        self.app.get(url, user=self.responsible, status=200)
        self.app.get(url, user=self.contributor, status=200)
        with run_in_staff_mode(self):
            self.app.get(url, user=self.manager, status=200)
        self.app.get(url, user=self.reviewer, status=403)
        self.app.get(url, user=self.student_external, status=403)


class TestTextAnswerExportView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = baker.make(
            UserProfile,
            email="reviewer@institution.example.com",
            groups=[Group.objects.get(name="Reviewer")],
        )
        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED)
        cache_results(evaluation)

        cls.url = f"/results/evaluation/{evaluation.id}/text_answers_export"

    def test_file_sent(self):
        def mock(_self, res):
            res.write(b"1337")

        with patch.object(TextAnswerExporter, "export", mock):
            with run_in_staff_mode(self):
                response = self.app.get(self.url, user=self.reviewer, status=200)
                self.assertEqual(response.headers["Content-Type"], "application/vnd.ms-excel")
                self.assertEqual(response.content, b"1337")

    @patch("evap.results.exporters.TextAnswerExporter.export")
    def test_permission_denied(self, export_method):
        manager = make_manager()
        student = baker.make(UserProfile, email="student@institution.example.com")

        self.app.get(self.url, user=student, status=403)
        export_method.assert_not_called()

        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.reviewer, status=200)
            export_method.assert_called_once()

        export_method.reset_mock()
        with run_in_staff_mode(self):
            self.app.get(self.url, user=manager, status=200)
            export_method.assert_called_once()

    @patch("evap.results.exporters.TextAnswerExporter.export")
    def test_invalid_contributor_id(self, export_method):
        with run_in_staff_mode(self):
            self.app.get(self.url + "?contributor_id=1234", user=self.reviewer, status=404)
            self.app.get(self.url + "?contributor_id=", user=self.reviewer, status=400)
            self.app.get(self.url + "?contributor_id=asd", user=self.reviewer, status=400)
            export_method.assert_not_called()
