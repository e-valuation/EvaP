from datetime import date, datetime
from typing import Any

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.expected_conditions import (
    element_to_be_clickable,
    invisibility_of_element_located,
    text_to_be_present_in_element_value,
    visibility_of_element_located,
)
from selenium.webdriver.support.relative_locator import locate_with

from evap.evaluation.models import (
    Contribution,
    Course,
    Evaluation,
    Program,
    Question,
    QuestionAssignment,
    Questionnaire,
    QuestionType,
    Semester,
    UserProfile,
)
from evap.evaluation.tests.tools import LiveServerTest, classes_of_element


class TomselectMixin:

    def select_tomselect_option(self, select: WebElement, option: str) -> None:
        assert isinstance(self, LiveServerTest)
        tomselect_options: Any = select.get_property("tomselect")["options"]  # type: ignore[index]
        target_options = [key for key, value in tomselect_options.items() if value["text"] == option]
        self.assertEqual(len(target_options), 1)
        self.selenium.execute_script("arguments[0].tomselect.setValue(arguments[1])", select, target_options[0])

    def input_from_tomselect(self, select: WebElement) -> WebElement:
        assert isinstance(self, LiveServerTest)
        return self.selenium.find_element(locate_with(By.CSS_SELECTOR, "div[data-value]").to_right_of(select))


class EvaluationEditLiveTest(LiveServerTest, TomselectMixin):
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

        general_questionnaire = baker.make(Questionnaire, question_assignments=[baker.make(QuestionAssignment)])
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
        self.select_tomselect_option(row, "manager (manager@institution.example.com)")

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
        baker.make(Evaluation, course=course, name_en="evaluation name")

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:semester_view", args=[semester.pk]))

        search_input = self.wait.until(
            visibility_of_element_located((By.CSS_SELECTOR, "input[type='search'][name='search-evaluation']"))
        )
        search_input.clear()
        search_input.send_keys("course name")

        self.wait.until(
            visibility_of_element_located(
                (By.XPATH, "//button[@slot='show-button' and @aria-label='Create exam evaluation']")
            )
        )

        search_input.clear()
        search_input.send_keys("exam")

        self.wait.until(invisibility_of_element_located((By.XPATH, "//td//a[contains(text(),'course name')]")))


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


class QuestionnaireEditLiveTest(LiveServerTest, TomselectMixin):

    def setUp(self) -> None:
        super().setUp()
        self.questionnaire = baker.make(Questionnaire)
        baker.make(QuestionAssignment, questionnaire=self.questionnaire, question__type=QuestionType.TEXT)

        self.url = self.reverse("staff:questionnaire_edit", args=[self.questionnaire.pk])

    def first_question_row(self) -> dict[str, WebElement]:
        elements: Any = self.selenium.find_elements(By.CSS_SELECTOR, "[id^='id_question_assignments-0-']")
        return {element.get_attribute("id").split("-")[-1]: element for element in elements}

    def test_edit_question(self) -> None:
        new_question = baker.make(Question, type=QuestionType.GRADE, allows_additional_textanswers=True)

        with self.enter_staff_mode():
            self.selenium.get(self.url)

        row = self.first_question_row()

        self.assertNotEqual(row["question"].get_property("value"), str(new_question.pk))

        self.select_tomselect_option(row["text_de"], new_question.text_de)
        self.wait.until(
            text_to_be_present_in_element_value((By.ID, "id_question_assignments-0-question"), str(new_question.pk))
        )
        self.assertEqual(self.input_from_tomselect(row["text_de"]).text, new_question.text_de)
        self.assertEqual(
            row["allows_additional_textanswers"].get_property("checked"), new_question.allows_additional_textanswers
        )
        self.assertEqual(row["type"].get_property("value"), str(new_question.type))

        submit_btn = self.wait.until(element_to_be_clickable((By.ID, "questionnaire-save-btn")))

        with self.enter_staff_mode():
            submit_btn.click()

        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.questions.count(), 1)
        self.assertEqual(self.questionnaire.question_assignments.get().order, 0)
        self.assertEqual(self.questionnaire.questions.get(), new_question)

    def test_question_override(self) -> None:
        new_question_text_de = "Neue Frage"
        new_question_text_en = "New Question"
        with self.enter_staff_mode():
            self.selenium.get(self.url)

        row = self.first_question_row()

        add_option_script = (
            "arguments[0].tomselect.addOption({'value': JSON.stringify({'value':arguments[1]}),'text':arguments[1]})"
        )
        self.selenium.execute_script(add_option_script, row["text_de"], new_question_text_de)
        self.selenium.execute_script(add_option_script, row["text_en"], new_question_text_en)
        self.select_tomselect_option(row["text_de"], new_question_text_de)
        self.select_tomselect_option(row["text_en"], new_question_text_en)

        self.wait.until(lambda _: self.input_from_tomselect(row["text_de"]).text == new_question_text_de)
        self.wait.until(lambda _: self.input_from_tomselect(row["text_en"]).text == new_question_text_en)

        self.assertEqual(row["question"].get_property("value"), "")

        submit_btn = self.wait.until(element_to_be_clickable((By.ID, "questionnaire-save-btn")))

        with self.enter_staff_mode():
            submit_btn.click()

        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.questions.count(), 1)
        self.assertEqual(self.questionnaire.question_assignments.get().order, 0)
        new_question = self.questionnaire.questions.get()
        self.assertEqual(new_question.text_de, new_question_text_de)
        self.assertEqual(new_question.text_en, new_question_text_en)
