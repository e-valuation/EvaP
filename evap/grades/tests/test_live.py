from model_bakery import baker

from evap.evaluation.models import Course, Evaluation, Group, Semester
from evap.evaluation.tests.tools import VisualRegressionTestCase


class GradesViewTest(VisualRegressionTestCase):
    def test_grades_semester_view(self):
        baker.seed(31902)

        semester = baker.make(Semester)

        self.manager.groups.add(Group.objects.get(name="Grade publisher"))
        with self.enter_staff_mode():
            self.selenium.get(self.reverse("grades:semester_view", args=[semester.id]))
            self.trigger_screenshot("grades:semester - no courses")

            courses = baker.make(Course, semester=semester, _quantity=30)
            baker.make(
                Evaluation,
                course=iter(courses),
                wait_for_grade_upload_before_publishing=True,
                state=Evaluation.State.IN_EVALUATION,
                _quantity=len(courses),
            )
            self.selenium.get(self.reverse("grades:semester_view", args=[semester.id]))

            self.trigger_screenshot("grades:semester - 30 courses")
