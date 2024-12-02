from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from evap.evaluation.models import Contribution, Course, Evaluation, Program, Question, Questionnaire, UserProfile
from evap.evaluation.tests.tools import LiveServerTest, make_manager


class StaffLiveTests(LiveServerTest):

    def test_changes_form_data(self):
        manager = make_manager()
        responsible = baker.make(UserProfile)
        editor = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )

        baker.make(Questionnaire, questions=[baker.make(Question)])
        general_question = baker.make(Question)
        general_questionnaire = baker.make(Questionnaire, questions=[general_question])
        evaluation.general_contribution.questionnaires.set([general_questionnaire])
        contributor_question = baker.make(Question)
        contributor_questionnaire = baker.make(
            Questionnaire,
            type=Questionnaire.Type.CONTRIBUTOR,
            questions=[contributor_question],
        )
        contribution1 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        contribution2 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=editor,
            order=1,
            role=Contribution.Role.EDITOR,
        )
        contribution1.questionnaires.set([contributor_questionnaire])
        contribution2.questionnaires.set([contributor_questionnaire])

        self._login(manager)

        self._enter_staff_mode()

        self.selenium.get(self.live_server_url + reverse("staff:evaluation_edit", args=[evaluation.pk]))

        self._screenshot("changes_form_data")

        self.wait.until(
            expected_conditions.visibility_of_element_located((By.XPATH, "//label[contains(text(), 'Editor')]"))
        )

        manager_id = self.selenium.execute_script(
            """
            const tomselect = document.getElementById("id_contributions-0-contributor").tomselect;
            const options = tomselect.options;
            const managerOption = Object.keys(options).find(
                key => options[key].text == "manager (manager@institution.example.com)",
            );
            tomselect.setValue(managerOption);
            return managerOption;
        """
        )

        editor_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Editor')]")
        own_and_general_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Own and general')]")

        editor_labels[0].click()
        own_and_general_labels[0].click()

        form_data = self.selenium.execute_script(
            """
                return Object.fromEntries(new FormData(document.getElementById("evaluation-form")));
            """
        )
        assert form_data["contributions-0-contributor"] == manager_id
        assert form_data["contributions-0-order"] == "0"
        assert form_data["contributions-0-role"] == "1"
        assert form_data["contributions-0-textanswer_visibility"] == "GENERAL"
