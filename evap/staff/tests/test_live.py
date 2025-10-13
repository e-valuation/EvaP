import time
from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.expected_conditions import element_to_be_clickable, visibility_of_element_located

from evap.evaluation.models import Contribution, Course, Evaluation, Program, Question, Questionnaire, UserProfile
from evap.evaluation.tests.tools import LiveServerTest

from visual_regression_tracker import VisualRegressionTracker, Config, TestRun, IgnoreArea

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
            self.selenium.get(self.live_server_url + reverse("staff:evaluation_edit", args=[evaluation.pk]))

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

class StaffSemesterViewRegressionTest(LiveServerTest):

    def test_regression(self):
        vrt = VisualRegressionTracker()

        baker.seed(31902)

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="en",
        )
        evaluation2 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=evaluation.course.semester, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="en",
        )
        evaluation3 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=evaluation.course.semester, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            main_language="de",
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

        with vrt:
            with self.enter_staff_mode():
                self.selenium.get(self.live_server_url + reverse("staff:semester_view", args=[evaluation.course.semester_id]))


                _ = self.wait.until(
                    expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '#evaluation-filter-buttons .badge'))
                )

                vrt.track(TestRun(
                    name='staff:index',
                    imageBase64=self.selenium.get_screenshot_as_base64(),
                    diffTollerancePercent=0,
                    os='Linux',
                    browser='Firefox',
                    viewport=self.viewport,
                    device='PC',
                    ignoreAreas=[IgnoreArea(y=3968, height=42, x=0, width=1920)]
                ))



