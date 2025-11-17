from django.test import override_settings
from freezegun import freeze_time
from model_bakery import baker

from evap.evaluation.models import Course, Evaluation, Group, Semester
from evap.evaluation.tests.tools import VisualRegressionTestCase


class GradesViewTest(VisualRegressionTestCase):

    @freeze_time("2025-10-27")
    @override_settings(SLOGANS_EN=["Einigermaßen verlässlich aussehende Pixeltestung"])
    def test_grades_semester_view(self):
        baker.seed(31902)

        semester = baker.make(Semester)

        self.manager.groups.add(Group.objects.get(name="Grade publisher"))
        with self.enter_staff_mode():
            self.selenium.get(self.reverse("grades:semester_view", args=[semester.id]))
            self.trigger_screenshot("grades:semester - no courses")

            courses = baker.make(Course, semester=semester, _quantity=30)
            _ = [
                baker.make(
                    Evaluation,
                    course=course,
                    wait_for_grade_upload_before_publishing=True,
                    state=Evaluation.State.IN_EVALUATION,
                )
                for course in courses
            ]
            self.selenium.get(self.reverse("grades:semester_view", args=[semester.id]))

            self.trigger_screenshot("grades:semester - 30 courses")
