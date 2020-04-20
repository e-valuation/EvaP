from datetime import date, datetime, timedelta

from django.core import mail
from django.contrib.auth.models import Group

from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, Questionnaire, Semester, UserProfile


class GradeUploadTest(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        baker.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        cls.student = baker.make(UserProfile, username="student", email="student@institution.example.com")
        cls.student2 = baker.make(UserProfile, username="student2", email="student2@institution.example.com")
        cls.student3 = baker.make(UserProfile, username="student3", email="student3@institution.example.com")
        editor = baker.make(UserProfile, username="editor", email="editor@institution.example.com")

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

        contribution = baker.make(Contribution, evaluation=cls.evaluation, contributor=editor, can_edit=True,
                                  textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        contribution.questionnaires.set([baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)])

        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

    def tearDown(self):
        for course in Course.objects.all():
            for grade_document in course.grade_documents.all():
                grade_document.file.delete()

    def helper_upload_grades(self, course, final_grades):
        upload_files = [('file', 'grades.txt', b"Some content")]

        final = "?final=true" if final_grades else ""
        response = self.app.post(
            "/grades/semester/{}/course/{}/upload{}".format(course.semester.id, course.id, final),
            params={"description_en": "Grades", "description_de": "Grades"},
            user="grade_publisher",
            content_type='multipart/form-data',
            upload_files=upload_files,
        ).follow()
        return response

    def helper_check_final_grade_upload(self, course, expected_number_of_emails):
        response = self.helper_upload_grades(course, final_grades=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Successfully", response)
        self.assertEqual(course.final_grade_documents.count(), 1)
        self.assertEqual(len(mail.outbox), expected_number_of_emails)
        response = self.app.get("/grades/download/{}".format(course.final_grade_documents.first().id), user="student")
        self.assertEqual(response.status_code, 200)

        # tear down
        course.final_grade_documents.first().file.delete()
        course.final_grade_documents.first().delete()
        mail.outbox.clear()

    def test_upload_midterm_grades(self):
        self.assertEqual(self.course.midterm_grade_documents.count(), 0)

        response = self.helper_upload_grades(self.course, final_grades=False)
        self.assertEqual(response.status_code, 200)
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
        evaluation.evaluation_begin()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: evaluated
        evaluation.evaluation_end()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: reviewed
        evaluation.review_finished()
        evaluation.save()
        self.helper_check_final_grade_upload(
            course, evaluation.num_participants + evaluation.contributions.exclude(contributor=None).count())

        # state: published
        evaluation.publish()
        evaluation.save()
        self.helper_check_final_grade_upload(course, 0)

    def test_toggle_no_grades(self):
        evaluation = baker.make(
            Evaluation,
            name_en="Toggle",
            vote_start_datetime=datetime.now(),
            state="reviewed",
            participants=[self.student, self.student2, self.student3],
            voters=[self.student, self.student2]
        )
        contribution = Contribution(evaluation=evaluation, contributor=UserProfile.objects.get(username="editor"),
                                    can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        contribution.save()
        contribution.questionnaires.set([baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)])

        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        self.assertFalse(evaluation.course.gets_no_grade_documents)

        response = self.app.post("/grades/toggle_no_grades", params={"course_id": evaluation.course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertTrue(evaluation.course.gets_no_grade_documents)
        # evaluation should get published here
        self.assertEqual(evaluation.state, "published")
        self.assertEqual(len(mail.outbox), evaluation.num_participants + evaluation.contributions.exclude(contributor=None).count())

        response = self.app.post("/grades/toggle_no_grades", params={"course_id": evaluation.course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        evaluation = Evaluation.objects.get(id=evaluation.id)
        self.assertFalse(evaluation.course.gets_no_grade_documents)

    def test_grade_document_download_after_archiving(self):
        # upload grade document
        self.helper_upload_grades(self.course, final_grades=False)
        self.assertGreater(self.course.midterm_grade_documents.count(), 0)

        url = "/grades/download/" + str(self.course.midterm_grade_documents.first().id)
        self.app.get(url, user="student", status=200)  # grades should be downloadable

        self.semester.delete_grade_documents()
        self.app.get(url, user="student", status=404)  # grades should not be downloadable anymore


class GradeDocumentIndexTest(WebTest):
    url = '/grades/'

    @classmethod
    def setUpTestData(cls):
        baker.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        cls.semester = baker.make(Semester, grade_documents_are_deleted=False)
        cls.archived_semester = baker.make(Semester, grade_documents_are_deleted=True)

    def test_visible_semesters(self):
        page = self.app.get(self.url, user="grade_publisher", status=200)
        self.assertIn(self.semester.name, page)
        self.assertNotIn(self.archived_semester.name, page)


class GradeSemesterViewTest(WebTest):
    url = '/grades/semester/1'

    @classmethod
    def setUpTestData(cls):
        baker.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])

    def test_does_not_crash(self):
        semester = baker.make(Semester, pk=1, grade_documents_are_deleted=False)
        course = baker.make(Course, semester=semester)
        baker.make(Evaluation, course=course, state="prepared")
        page = self.app.get(self.url, user="grade_publisher", status=200)
        self.assertIn(course.name, page)

    def test_403_on_deleted(self):
        baker.make(Semester, pk=1, grade_documents_are_deleted=True)
        self.app.get('/grades/semester/1', user="grade_publisher", status=403)


class GradeCourseViewTest(WebTest):
    url = '/grades/semester/1/course/1'

    @classmethod
    def setUpTestData(cls):
        baker.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])

    def test_does_not_crash(self):
        semester = baker.make(Semester, pk=1, grade_documents_are_deleted=False)
        baker.make(Evaluation, course=baker.make(Course, pk=1, semester=semester), state="prepared")
        self.app.get('/grades/semester/1/course/1', user="grade_publisher", status=200)

    def test_403_on_archived_semester(self):
        archived_semester = baker.make(Semester, pk=1, grade_documents_are_deleted=True)
        baker.make(Evaluation, course=baker.make(Course, pk=1, semester=archived_semester), state="prepared")
        self.app.get('/grades/semester/1/course/1', user="grade_publisher", status=403)
