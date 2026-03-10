from model_bakery import baker

from evap.cms.models import EvaluationLink
from evap.evaluation.models import Evaluation, Semester, UserProfile
from evap.evaluation.tests.tools import make_manager
from evap.staff.tests.utils import WebTestStaffMode


class TestEvaluationMerge(WebTestStaffMode):
    def test_merge_evaluations(self):
        semester = baker.make(Semester)
        manager = make_manager()

        students_1 = baker.make(UserProfile, _quantity=2)
        students_2 = baker.make(UserProfile, _quantity=3)
        students_2.append(students_1[0])  # add duplicate

        main_evaluation = baker.make(Evaluation, course__semester=semester, participants=students_1)
        other_evaluation = baker.make(Evaluation, course__semester=semester, participants=students_2)

        baker.make(EvaluationLink, evaluation=main_evaluation, cms_id="0x1")
        baker.make(EvaluationLink, evaluation=other_evaluation, cms_id="0x2")

        url = f"/cms/evaluation_merge_selection/{main_evaluation.pk}"

        self.assertEqual(main_evaluation.participants.count(), 2)
        self.assertEqual(other_evaluation.participants.count(), 4)

        page = self.app.get(url, user=manager, status=200)
        form = page.forms["evaluation-merge-form"]
        form["other_evaluation"] = other_evaluation.pk
        response = form.submit().follow()

        self.assertIn("Successfully merged", response)

        main_evaluation = Evaluation.objects.get(pk=main_evaluation.pk)
        self.assertEqual(main_evaluation.participants.count(), 5)
        self.assertEqual(main_evaluation.evaluation_links.count(), 2)
        self.assertFalse(Evaluation.objects.filter(pk=other_evaluation.pk).exists())
