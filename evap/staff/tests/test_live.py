from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.expected_conditions import (
    element_to_be_clickable,
    invisibility_of_element_located,
    visibility_of_element_located,
)

from evap.evaluation.models import (
    Contribution,
    Course,
    Evaluation,
    Program,
    Question,
    Questionnaire,
    Semester,
    UserProfile,
)
from evap.evaluation.tests.tools import LiveServerTest, VisualRegressionTestCase, classes_of_element


class EvaluationEditLiveTest(LiveServerTest):
    def test_submit_changes_form_data(self):
        """Regression test for #1769"""

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="en",
        )

        general_questionnaire = baker.make(Questionnaire, questions=[baker.make(Question)])
        evaluation.general_contribution.questionnaires.set([general_questionnaire])

        contribution1 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.CONTRIBUTOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=baker.make(UserProfile),
            order=1,
            role=Contribution.Role.EDITOR,
        )

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:evaluation_edit", args=[evaluation.pk]))

        row = self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, "#id_contributions-0-contributor")))
        tomselect_options = row.get_property("tomselect")["options"]
        manager_text = "manager (manager@institution.example.com)"
        manager_options = [key for key, value in tomselect_options.items() if value["text"] == manager_text]
        self.assertEqual(len(manager_options), 1)
        self.selenium.execute_script(
            f"""let tomselect = document.querySelector("#id_contributions-0-contributor").tomselect;
            tomselect.setValue("{manager_options[0]}");"""
        )

        submit_btn = self.wait.until(
            element_to_be_clickable((By.XPATH, "//button[@name='operation' and @value='save']"))
        )

        editor_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Editor')]")
        own_and_general_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Own and general')]")
        editor_labels[0].click()
        own_and_general_labels[0].click()

        with self.enter_staff_mode():
            submit_btn.click()

        contribution1.refresh_from_db()

        self.assertEqual(contribution1.contributor_id, self.manager.id)
        self.assertEqual(contribution1.order, 0)
        self.assertEqual(contribution1.role, Contribution.Role.EDITOR)
        self.assertEqual(contribution1.textanswer_visibility, Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)

    def test_staff_semester_view_columns_not_searchable(self):
        """Regression test for #2461"""

        semester = baker.make(Semester)
        course = baker.make(Course, semester=semester, name_en="course name")
        baker.make(Evaluation, course=course, name_en="evaluation name searchable-needle")

        evaluation_element = (By.XPATH, "//a[contains(text(),'searchable-needle')]")

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:semester_view", args=[semester.pk]))

        search_input = self.wait.until(
            visibility_of_element_located((By.CSS_SELECTOR, "input[type='search'][name='search-evaluation']"))
        )
        search_input.clear()
        search_input.send_keys("course name")

        self.wait.until(visibility_of_element_located(evaluation_element), "Evaluation should be searchable.")

        self.wait.until(
            visibility_of_element_located(
                (By.XPATH, "//button[@slot='show-button' and @aria-label='Create exam evaluation']")
            )
        )

        search_input.clear()
        search_input.send_keys("exam")

        self.wait.until(
            invisibility_of_element_located(evaluation_element), "Searching for 'exam' should not yield results."
        )


class ParticipantCollapseTests(LiveServerTest):
    def test_collapse_with_editor_approved(self) -> None:
        participants = baker.make(UserProfile, _quantity=20)
        baker.make(UserProfile, last_name="participant")

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            participants=participants,
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            state=Evaluation.State.EDITOR_APPROVED,
        )

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:evaluation_edit", args=[evaluation.id]))

        card_header = self.selenium.find_element(By.CSS_SELECTOR, ".card:has(#id_participants) .card-header")
        self.assertIn("collapsed", classes_of_element(card_header))

        card_header.click()
        self.assertNotIn("collapsed", classes_of_element(card_header))

        counter = card_header.find_element(By.CSS_SELECTOR, ".rounded-pill")
        self.assertEqual(counter.text, "20")

        tomselect_input = self.selenium.find_element(By.CSS_SELECTOR, "input#id_participants-ts-control")
        tomselect_input.click()
        tomselect_input.send_keys("participant")
        self.selenium.find_element(By.CSS_SELECTOR, ".option.active").click()
        self.assertEqual(counter.text, "21")

        random_participant_remove_button = self.selenium.find_element(
            By.CSS_SELECTOR, ".card:has(#id_participants) a.remove"
        )
        random_participant_remove_button.click()
        self.assertEqual(counter.text, "20")

    def test_collapse_without_editor_approved(self) -> None:
        responsible = baker.make(UserProfile, last_name="responsible")
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            state=Evaluation.State.NEW,
        )

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:evaluation_edit", args=[evaluation.id]))

        card_header = self.selenium.find_element(By.CSS_SELECTOR, ".card:has(#id_participants) .card-header")
        self.assertNotIn("collapsed", classes_of_element(card_header))
        card_header.click()
        self.assertIn("collapsed", classes_of_element(card_header))

        counter = card_header.find_element(By.CSS_SELECTOR, ".rounded-pill")
        self.assertEqual(counter.text, "0")


class StaffSemesterViewRegressionTest(VisualRegressionTestCase):

    def test_regression(self):
        baker.seed(31902)

        responsible = baker.make(UserProfile, last_name="aResponsibleUser")
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            course__responsibles=[responsible],
            course__programs=[program],
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="en",
        )
        baker.make(
            Evaluation,
            course__semester=evaluation.course.semester,
            course__programs=[program],
            course__responsibles=[responsible],
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="en",
        )

        general_questionnaire = baker.make(Questionnaire, questions=[baker.make(Question)])
        baker.make(
            Evaluation,
            course__semester=evaluation.course.semester,
            course__programs=[program],
            course__responsibles=[responsible],
            general_contribution__questionnaires=[general_questionnaire],
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="de",
        )

        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.CONTRIBUTOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=baker.make(UserProfile),
            order=1,
            role=Contribution.Role.EDITOR,
        )

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:semester_view", args=[evaluation.course.semester_id]))

            self.wait.until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "#evaluation-filter-buttons .badge"))
            )

            self.trigger_screenshot("staff:index")
