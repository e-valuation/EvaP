from django.core import mail
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import text_to_be_present_in_element, visibility_of_element_located

from evap.evaluation.models import Course, UserProfile
from evap.evaluation.tests.tools import LiveServerTest, UserProfileSearchLiveServerTest


class ContactModalTests(LiveServerTest):
    def test_contact_modal(self) -> None:
        self.selenium.get(self.reverse("evaluation:index"))
        self.selenium.find_element(By.ID, "feedbackModalShowButton").click()
        self.wait.until(visibility_of_element_located((By.ID, "feedbackModalMessageText")))
        self.selenium.find_element(By.ID, "feedbackModalMessageText").send_keys("Test message")
        self.selenium.find_element(By.ID, "feedbackModalActionButton").click()

        self.wait.until(
            text_to_be_present_in_element(
                (By.CSS_SELECTOR, "#successMessageModal_feedbackModal .modal-body"),
                "Your message was successfully sent.",
            )
        )
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].subject, f"[EvaP] Message from {self.manager.email}")


class ProfileUserProfileSearchTest(UserProfileSearchLiveServerTest):
    def test_profile_set_delegates(self) -> None:
        """Test delegates field in ProfileForm."""
        possible_delegate = baker.make(
            UserProfile, first_name_given="Jane", last_name="Doe", email="test@institution.example.com"
        )
        not_active_user = baker.make(
            UserProfile,
            first_name_given="User 1",
            last_name="User 1",
            email="user1@institution.example.com",
            is_active=False,
        )
        is_proxy_user = baker.make(
            UserProfile,
            first_name_given="User 2",
            last_name="User 2",
            email="user2@institution.example.com",
            is_proxy_user=True,
        )

        active_user = baker.make(UserProfile)
        baker.make(Course, responsibles=[active_user])

        self.login(active_user)
        self.selenium.get(self.reverse("evaluation:profile_edit"))

        self.conduct_user_profile_search_test("delegates", [possible_delegate], [not_active_user, is_proxy_user])
