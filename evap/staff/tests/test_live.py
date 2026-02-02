from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    element_to_be_clickable,
    invisibility_of_element_located,
    visibility_of_element_located,
)
from selenium.webdriver.support.wait import WebDriverWait

from evap.evaluation.models import (
    Contribution,
    Course,
    Evaluation,
    Program,
    Question,
    Questionnaire,
    QuestionType,
    Semester,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tests.tools import LiveServerTest, classes_of_element


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


class QuestionnaireFormLiveTest(LiveServerTest):
    def test_question_type_disabling_logic(self):
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.POSITIVE_LIKERT)

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:questionnaire_edit", args=[questionnaire.pk]))

        # Part 1: Edit Existing Question
        row = self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, "#question_table tbody tr")))
        type_select = row.find_element(By.CSS_SELECTOR, "select[id$='-type']")

        self.assert_question_type_controls(
            row,
            type_select,
            QuestionType.TEXT,
            allows_additional_textanswers_disabled=True,
            counts_for_grade_disabled=True,
        )

        self.assert_question_type_controls(
            row,
            type_select,
            QuestionType.POSITIVE_LIKERT,
            allows_additional_textanswers_disabled=False,
            counts_for_grade_disabled=False,
        )

        self.assert_question_type_controls(
            row,
            type_select,
            QuestionType.HEADING,
            allows_additional_textanswers_disabled=True,
            counts_for_grade_disabled=True,
        )

        # Part 2: Add New Question
        self.selenium.find_element(By.CLASS_NAME, "add-row").click()

        # Wait until there are at least 3 rows (2 existing (since there is the default new row) + 1 new)
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#question_table tbody tr")) >= 3)

        new_row = self.selenium.find_elements(By.CSS_SELECTOR, "#question_table tbody tr")[
            -2
        ]  # the last row is the add row button
        new_type_select = new_row.find_element(By.CSS_SELECTOR, "select[id$='-type']")

        self.assert_question_type_controls(
            new_row,
            new_type_select,
            QuestionType.TEXT,
            allows_additional_textanswers_disabled=True,
            counts_for_grade_disabled=True,
        )

        self.assert_question_type_controls(
            new_row,
            new_type_select,
            QuestionType.POSITIVE_LIKERT,
            allows_additional_textanswers_disabled=False,
            counts_for_grade_disabled=False,
        )

        self.assert_question_type_controls(
            new_row,
            new_type_select,
            QuestionType.HEADING,
            allows_additional_textanswers_disabled=True,
            counts_for_grade_disabled=True,
        )

    def test_questionnaire_type_disabling_logic(self):
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.POSITIVE_LIKERT)

        with self.enter_staff_mode():
            self.selenium.get(self.reverse("staff:questionnaire_edit", args=[questionnaire.pk]))

        row = self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, "#question_table tbody tr")))
        questionnaire_type_select = self.selenium.find_element(By.ID, "id_type")

        # Change to Dropout
        self.select_tom_select_option(questionnaire_type_select, str(Questionnaire.Type.DROPOUT))
        self.assertTrue(row.find_element(By.CSS_SELECTOR, "input[id$='-counts_for_grade']").get_attribute("disabled"))
        self.assertFalse(
            row.find_element(By.CSS_SELECTOR, "input[id$='-allows_additional_textanswers']").get_attribute("disabled")
        )

        # Change back to Top
        self.select_tom_select_option(questionnaire_type_select, str(Questionnaire.Type.TOP))
        self.assertFalse(row.find_element(By.CSS_SELECTOR, "input[id$='-counts_for_grade']").get_attribute("disabled"))
        self.assertFalse(
            row.find_element(By.CSS_SELECTOR, "input[id$='-allows_additional_textanswers']").get_attribute("disabled")
        )

    def select_tom_select_option(self, select_element, value):
        self.selenium.execute_script(f"arguments[0].tomselect.setValue('{value}');", select_element)

    def assert_question_type_controls(
        self,
        row,
        type_select,
        question_type,
        *,
        allows_additional_textanswers_disabled,
        counts_for_grade_disabled,
    ):
        self.select_tom_select_option(type_select, str(question_type))
        self.assertEqual(
            allows_additional_textanswers_disabled,
            bool(
                row.find_element(By.CSS_SELECTOR, "input[id$='-allows_additional_textanswers']").get_attribute(
                    "disabled"
                )
            ),
        )
        self.assertEqual(
            counts_for_grade_disabled,
            bool(row.find_element(By.CSS_SELECTOR, "input[id$='-counts_for_grade']").get_attribute("disabled")),
        )


class TextAnswerEditLiveTest(LiveServerTest):
    def test_edit_textanswer_redirect(self):
        """Regression test for #1696"""

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            state=Evaluation.State.EVALUATED,
            can_publish_text_results=True,
        )

        question1 = baker.make(Question)

        general_questionnaire = baker.make(Questionnaire, questions=[question1])
        evaluation.general_contribution.questionnaires.set([general_questionnaire])

        contribution1 = baker.make(
            Contribution, evaluation=evaluation, contributor=None, questionnaires=[general_questionnaire]
        )

        baker.make(
            TextAnswer,
            question=question1,
            contribution=contribution1,
            answer=iter(f"this is a dummy answer {i}" for i in range(3)),
            original_answer=None,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED,
            _quantity=3,
        )

        textanswer1 = baker.make(
            TextAnswer,
            question=question1,
            contribution=contribution1,
            answer="this answer will be edited",
            original_answer=None,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED,
        )

        baker.make(
            TextAnswer,
            question=question1,
            contribution=contribution1,
            answer=iter(f"this is a dummy answer {i}" for i in range(3, 6)),
            original_answer=None,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED,
            _quantity=3,
        )

        with self.enter_staff_mode():
            self.selenium.get(
                self.reverse("staff:evaluation_textanswers", query={"view": "quick"}, args=[evaluation.pk])
            )

        next_textanswer_btn = self.selenium.find_element(By.XPATH, "//span[@data-slide='right']")
        edit_btn = self.selenium.find_element(By.ID, "textanswer-edit-btn")

        while True:
            try:
                WebDriverWait(self.selenium, 1).until(
                    visibility_of_element_located((By.ID, f"textanswer-{str(textanswer1.pk)}"))
                )
                break
            except TimeoutException:
                next_textanswer_btn.click()

        with self.enter_staff_mode():
            edit_btn.click()

        textanswer_field = self.selenium.find_element(By.XPATH, "//textarea[@name='answer']")
        submit_btn = self.selenium.find_element(By.ID, "textanswer-edit-submit-button")

        textanswer_field.clear()
        textanswer_field.send_keys("edited answer")

        with self.enter_staff_mode():
            submit_btn.click()

        self.wait.until(visibility_of_element_located((By.XPATH, "//div[contains(text(), 'edited answer')]")))
        self.wait.until(
            invisibility_of_element_located((By.XPATH, "//div[contains(text(), 'this is a dummy answer')]"))
        )
