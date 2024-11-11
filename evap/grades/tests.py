from datetime import date, datetime, timedelta

from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, Questionnaire, Semester, UserProfile
from evap.evaluation.tests.tools import WebTest, WebTestWith200Check
from evap.grades.models import GradeDocument


def make_grade_publisher():
    return baker.make(
        UserProfile,
        email="grade_publisher@institution.example.com",
        groups=[Group.objects.get(name="Grade publisher")],
    )


class GradeUploadTest(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.grade_publisher = make_grade_publisher()
        cls.student = baker.make(UserProfile, email="student@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@institution.example.com")
        cls.student3 = baker.make(UserProfile, email="student3@institution.example.com")
        editor = baker.make(UserProfile, email="editor@institution.example.com")

        cls.semester = baker.make(Semester, grade_documents_are_deleted=False)
        cls.course = baker.make(Course, semester=cls.semester)
        cls.evaluation = baker.make(
            Evaluation,
            course=cls.course,
            vote_start_datetime=datetime.now() - timedelta(days=10),
            vote_end_date=date.today() + timedelta(days=10),
            participants=[cls.student, cls.student2, cls.student3],
            voters=[cls.student, cls.student2],
        )

        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=editor,
            questionnaires=[baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

    def tearDown(self):
        for course in Course.objects.all():
            for grade_document in course.grade_documents.all():
                grade_document.file.delete()
        super().tearDown()

    def helper_upload_grades(self, course, final_grades):
        upload_files = [("file", "grades.txt", b"Some content")]

        final = "?final=true" if final_grades else ""
        return self.app.post(
            f"{reverse('grades:upload_grades', args=[course.id])}{final}",
            params={"description_en": "Grades", "description_de": "Grades"},
            user=self.grade_publisher,
            content_type="multipart/form-data",
            upload_files=upload_files,
        ).follow(status=200)

    def helper_check_final_grade_upload(self, course, expected_number_of_emails):
        response = self.helper_upload_grades(course, final_grades=True)
        self.assertIn("Successfully", response)
        self.assertEqual(course.final_grade_documents.count(), 1)
        self.assertEqual(len(mail.outbox), expected_number_of_emails)
        self.app.get(f"/grades/download/{course.final_grade_documents.first().id}", user=self.student, status=200)

        # tear down
        course.final_grade_documents.first().file.delete()
        course.final_grade_documents.first().delete()
        mail.outbox.clear()

    def test_upload_midterm_grades(self):
        self.assertEqual(self.course.midterm_grade_documents.count(), 0)

        response = self.helper_upload_grades(self.course, final_grades=False)
        self.assertIn("Successfully", response)
        self.assertEqual(self.course.midterm_grade_documents.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_upload_final_grades(self):
        course = self.course
        evaluation = self.evaluation
        self.assertEqual(course.final_grade_documents.count(), 0)

        # state: new
        self.helper_check_final_grade_upload(course, 0)

        # state: prepared
        evaluation.ready_for_editors()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: editor_approved
        evaluation.editor_approve()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: approved
        evaluation.manager_approve()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: in_evaluation
        evaluation.begin_evaluation()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: evaluated
        evaluation.end_evaluation()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: reviewed
        evaluation.end_review()
        evaluation.save()
        self.helper_check_final_grade_upload(
            course, evaluation.num_participants + evaluation.contributions.exclude(contributor=None).count()
        )

        # state: published
        evaluation.publish()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

    def test_set_no_grades(self):
        evaluation = self.evaluation
        evaluation.manager_approve()
        evaluation.begin_evaluation()
        evaluation.end_evaluation()
        evaluation.end_review()
        evaluation.save()

        self.assertFalse(evaluation.course.gets_no_grade_documents)

        self.app.post(
            "/grades/set_no_grades",
            params={"course_id": evaluation.course.id, "status": "1"},
            user=self.grade_publisher,
            status=200,
        )
        evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertTrue(evaluation.course.gets_no_grade_documents)
        # evaluation should get published here
        self.assertEqual(evaluation.state, Evaluation.State.PUBLISHED)
        self.assertEqual(
            len(mail.outbox), evaluation.num_participants + evaluation.contributions.exclude(contributor=None).count()
        )

        self.app.post(
            "/grades/set_no_grades",
            params={"course_id": evaluation.course.id, "status": "0"},
            user=self.grade_publisher,
            status=200,
        )
        evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertFalse(evaluation.course.gets_no_grade_documents)

        self.app.post(
            "/grades/set_no_grades",
            params={"course_id": evaluation.course.id, "status": "0"},
            user=self.grade_publisher,
            status=200,
        )
        evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertFalse(evaluation.course.gets_no_grade_documents)

    def test_grade_document_download_after_archiving(self):
        # upload grade document
        self.helper_upload_grades(self.course, final_grades=False)
        self.assertGreater(self.course.midterm_grade_documents.count(), 0)

        url = "/grades/download/" + str(self.course.midterm_grade_documents.first().id)
        self.app.get(url, user=self.student, status=200)  # grades should be downloadable

        self.semester.delete_grade_documents()
        self.app.get(url, user=self.student, status=404)  # grades should not be downloadable anymore


class GradeDocumentIndexTest(WebTest):
    url = "/grades/"

    @classmethod
    def setUpTestData(cls):
        cls.grade_publisher = make_grade_publisher()
        cls.semester = baker.make(Semester, grade_documents_are_deleted=False)
        cls.archived_semester = baker.make(Semester, grade_documents_are_deleted=True)

    def test_visible_semesters(self):
        page = self.app.get(self.url, user=self.grade_publisher, status=200)
        self.assertIn(self.semester.name, page)
        self.assertNotIn(self.archived_semester.name, page)


class GradeSemesterViewTest(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.grade_publisher = make_grade_publisher()
        cls.semester = baker.make(Semester, grade_documents_are_deleted=False)
        cls.evaluation = baker.make(Evaluation, course__semester=cls.semester, state=Evaluation.State.PREPARED)
        cls.url = f"/grades/semester/{cls.semester.pk}"

    def test_does_not_crash(self):
        page = self.app.get(self.url, user=self.grade_publisher, status=200)
        self.assertIn(self.evaluation.course.name, page)

    def test_403_on_deleted(self):
        self.semester.grade_documents_are_deleted = True
        self.semester.save()
        self.app.get(self.url, user=self.grade_publisher, status=403)


class GradeCourseViewTest(WebTestWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester, grade_documents_are_deleted=False)
        cls.evaluation = baker.make(Evaluation, course__semester=cls.semester, state=Evaluation.State.PREPARED)
        cls.grade_publisher = make_grade_publisher()

        cls.test_users = [cls.grade_publisher]
        cls.url = reverse("grades:course_view", args=[cls.evaluation.course.pk])

    def test_403_on_archived_semester(self):
        self.semester.grade_documents_are_deleted = True
        self.semester.save()
        self.app.get(self.url, user=self.grade_publisher, status=403)


class GradeEditTest(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls) -> None:
        cls.grade_publisher = make_grade_publisher()
        cls.grade_document = baker.make(GradeDocument)
        cls.url = reverse("grades:edit_grades", args=[cls.grade_document.pk])

    def test_edit_grades(self) -> None:
        previous_modifying_user = self.grade_document.last_modified_user
        self.assertNotEqual(previous_modifying_user, self.grade_publisher)
        response = self.app.get(self.url, user=self.grade_publisher)
        form = response.forms["grades-upload-form"]
        form["description_en"] = "Absolutely final grades"
        form["file"] = ("grades.txt", b"You did great!")
        form.submit()
        self.grade_document.refresh_from_db()
        self.assertEqual(self.grade_document.last_modified_user, self.grade_publisher)

    def test_grades_headlines(self) -> None:
        response = self.app.get(self.url, user=self.grade_publisher)
        self.assertContains(response, "Upload midterm grades")
        self.assertNotContains(response, "Upload final grades")

        self.grade_document.type = GradeDocument.Type.FINAL_GRADES
        self.grade_document.save()
        response = self.app.get(self.url, user=self.grade_publisher)
        self.assertContains(response, "Upload final grades")
        self.assertNotContains(response, "Upload midterm grades")


class GradeDeleteTest(WebTest):
    url = reverse("grades:delete_grades")
    csrf_checks = False

    def test_delete_grades(self):
        grade_publisher = make_grade_publisher()
        grade_document = baker.make(GradeDocument)

        post_params = {"grade_document_id": grade_document.id}
        self.app.post(self.url, user=grade_publisher, params=post_params, status=200)

        self.assertFalse(GradeDocument.objects.filter(pk=grade_document.pk).exists())
