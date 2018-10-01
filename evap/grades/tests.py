from datetime import date, datetime, timedelta

from django.core import mail
from django.contrib.auth.models import Group

from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Contribution, Semester
from evap.evaluation.tests.tools import WebTestWith200Check, WebTest


class GradeUploadTests(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        cls.student = mommy.make(UserProfile, username="student", email="student@institution.example.com")
        cls.student2 = mommy.make(UserProfile, username="student2", email="student2@institution.example.com")
        cls.student3 = mommy.make(UserProfile, username="student3", email="student3@institution.example.com")
        responsible = mommy.make(UserProfile, username="responsible", email="responsible@institution.example.com")

        cls.semester = mommy.make(Semester, grade_documents_are_deleted=False)
        cls.course = mommy.make(
            Course,
            name_en="Test",
            semester=cls.semester,
            vote_start_datetime=datetime.now() - timedelta(days=10),
            vote_end_date=date.today() + timedelta(days=10),
            participants=[cls.student, cls.student2, cls.student3],
            voters=[cls.student, cls.student2],
        )

        contribution = mommy.make(Contribution, course=cls.course, contributor=responsible, responsible=True,
                                  can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        contribution.questionnaires.set([mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)])

        cls.course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

    def setUp(self):
        self.course = Course.objects.get(pk=self.course.pk)

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
        self.assertEqual(course.final_grade_documents.count(), 0)

        # state: new
        self.helper_check_final_grade_upload(course, 0)

        # state: prepared
        course.ready_for_editors()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: editor_approved
        course.editor_approve()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: approved
        course.manager_approve()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: in_evaluation
        course.evaluation_begin()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: evaluated
        course.evaluation_end()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

        # state: reviewed
        course.review_finished()
        course.save()
        self.helper_check_final_grade_upload(
            course, course.num_participants + course.contributions.exclude(contributor=None).count())

        # state: published
        course.publish()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

    def test_toggle_no_grades(self):
        course = mommy.make(
            Course,
            name_en="Toggle",
            vote_start_datetime=datetime.now(),
            state="reviewed",
            participants=[self.student, self.student2, self.student3],
            voters=[self.student, self.student2]
        )
        contribution = Contribution(course=course, contributor=UserProfile.objects.get(username="responsible"),
                                    responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        contribution.save()
        contribution.questionnaires.set([mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)])

        course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        self.assertFalse(course.gets_no_grade_documents)

        response = self.app.post("/grades/toggle_no_grades", params={"course_id": course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        course = Course.objects.get(id=course.id)
        self.assertTrue(course.gets_no_grade_documents)
        # course should get published here
        self.assertEqual(course.state, "published")
        self.assertEqual(len(mail.outbox), course.num_participants + course.contributions.exclude(contributor=None).count())

        response = self.app.post("/grades/toggle_no_grades", params={"course_id": course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        course = Course.objects.get(id=course.id)
        self.assertFalse(course.gets_no_grade_documents)

    def test_grade_document_download_after_archiving(self):
        # upload grade document
        self.helper_upload_grades(self.course, final_grades=False)
        self.assertGreater(self.course.midterm_grade_documents.count(), 0)

        url = "/grades/download/" + str(self.course.midterm_grade_documents.first().id)
        self.app.get(url, user="student", status=200)  # grades should be downloadable

        self.semester.delete_grade_documents()
        self.app.get(url, user="student", status=404)  # grades should not be downloadable anymore


class GradeDocumentIndexTest(WebTestWith200Check):
    url = '/grades/'
    test_users = ['grade_publisher']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        cls.semester = mommy.make(Semester, grade_documents_are_deleted=False)
        cls.archived_semester = mommy.make(Semester, grade_documents_are_deleted=True)

    def test_visible_semesters(self):
        page = self.app.get(self.url, user="grade_publisher", status=200)
        self.assertIn(self.semester.name, page)
        self.assertNotIn(self.archived_semester.name, page)


class GradeDocumentSemesterWebTestWith200Check(WebTestWith200Check):
    url = '/grades/semester/1'
    test_users = ['grade_publisher']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        semester = mommy.make(Semester, pk=1, grade_documents_are_deleted=False)
        mommy.make(Semester, pk=2, grade_documents_are_deleted=True)
        cls.semester_course = mommy.make(Course, semester=semester, state="prepared")

    def test_semester_pages(self):
        page = self.app.get(self.url, user="grade_publisher", status=200)
        self.assertIn(self.semester_course.name, page)
        self.app.get('/grades/semester/2', user="grade_publisher", status=403)


class GradeDocumentCourseWebTestWith200Check(WebTestWith200Check):
    url = '/grades/semester/1/course/1'
    test_users = ['grade_publisher']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        semester = mommy.make(Semester, pk=1, grade_documents_are_deleted=False)
        archived_semester = mommy.make(Semester, pk=2, grade_documents_are_deleted=True)
        mommy.make(Course, pk=1, semester=semester, state="prepared")
        mommy.make(Course, pk=2, semester=archived_semester, state="prepared")

    def test_course_page(self):
        self.app.get('/grades/semester/2/course/2', user="grade_publisher", status=403)
