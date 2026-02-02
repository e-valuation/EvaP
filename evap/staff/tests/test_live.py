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


class EvaluationGridLiveTest(LiveServerTest):
    def test_evaluation_grid_sorting(self):
        test_semester = baker.make(Semester)

        baker.make(
            Evaluation,
            name_de="Evaluation 1",
            name_en="Evaluation 1",
            course=baker.make(Course, name_de="AE", name_en="Z", semester=test_semester),
        )
        baker.make(
            Evaluation,
            name_de="Evaluation 2",
            name_en="Evaluation 2",
            course=baker.make(Course, name_de="ÄB", name_en="ÜB", semester=test_semester),
        )
        baker.make(
            Evaluation,
            name_de="Evaluation 3",
            name_en="Evaluation 3",
            course=baker.make(Course, name_de="UE", name_en="UE", semester=test_semester),
        )
        baker.make(
            Evaluation,
            name_de="Evaluation 4",
            name_en="Evaluation 4",
            course=baker.make(Course, name_de="ÜB", name_en="ÄB", semester=test_semester),
        )
        baker.make(
            Evaluation,
            name_de="Evaluation 5",
            name_en="Evaluation 5",
            course=baker.make(Course, name_de="Z", name_en="AE", semester=test_semester),
        )

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:index"))

            language_de_button = self.selenium.find_element(
                By.XPATH,
                "//form[@action='/set_lang']//button[@data-set-spinner-icon='span-set-language-de']//parent::form",
            )

            language_de_button.submit()
            self.selenium.get(self.live_server_url + reverse("staff:semester_view", args=[test_semester.id]))
            self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, "#evaluation-table .col-order-asc")))

            table = self.selenium.find_element(By.ID, "evaluation-table").find_elements(
                By.XPATH, "//tbody//child::td[@data-col='name']"
            )

            self.assertEqual(table[0].get_attribute("data-order"), "ÄB – Evaluation 2")
            self.assertEqual(table[1].get_attribute("data-order"), "AE – Evaluation 1")
            self.assertEqual(table[2].get_attribute("data-order"), "ÜB – Evaluation 4")
            self.assertEqual(table[3].get_attribute("data-order"), "UE – Evaluation 3")
            self.assertEqual(table[4].get_attribute("data-order"), "Z – Evaluation 5")

            self.selenium.get(self.live_server_url + reverse("staff:index"))

            language_en_button = self.selenium.find_element(
                By.XPATH,
                "//form[@action='/set_lang']//button[@data-set-spinner-icon='span-set-language-en']//parent::form",
            )

            language_en_button.submit()
            self.selenium.get(self.live_server_url + reverse("staff:semester_view", args=[test_semester.id]))
            self.wait.until(visibility_of_element_located((By.ID, "evaluation-table")))

            toggle_sort_button = self.selenium.find_element(By.XPATH, "//thead//th[@data-col='name']")
            toggle_sort_button.click()
            self.wait.until(visibility_of_element_located((By.ID, "evaluation-table")))

            table = self.selenium.find_element(By.ID, "evaluation-table").find_elements(
                By.XPATH, "//tbody//child::td[@data-col='name']"
            )

            self.assertEqual(table[0].get_attribute("data-order"), "Z – Evaluation 1")
            self.assertEqual(table[1].get_attribute("data-order"), "UE – Evaluation 3")
            self.assertEqual(table[2].get_attribute("data-order"), "ÜB – Evaluation 2")
            self.assertEqual(table[3].get_attribute("data-order"), "AE – Evaluation 5")
            self.assertEqual(table[4].get_attribute("data-order"), "ÄB – Evaluation 4")


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
