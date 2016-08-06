import datetime

from django.core import mail
from django.contrib.auth.models import Group

from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Contribution
from evap.evaluation.tests.tools import WebTest
from evap.grades.models import SemesterGradeDownloadActivation


class GradeUploadTests(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        mommy.make(UserProfile, username="student", email="student@institution.example.com")
        mommy.make(UserProfile, username="student2", email="student2@institution.example.com")
        mommy.make(UserProfile, username="student3", email="student3@institution.example.com")
        responsible = mommy.make(UserProfile, username="responsible", email="responsible@institution.example.com")

        cls.course = mommy.make(Course,
            name_en="Test",
            vote_start_date=datetime.date.today(),
            participants=[
                UserProfile.objects.get(username="student"),
                UserProfile.objects.get(username="student2"),
                UserProfile.objects.get(username="student3"),
            ],
            voters=[
                UserProfile.objects.get(username="student"),
                UserProfile.objects.get(username="student2"),
            ]
        )
        contribution = Contribution(course=cls.course, contributor=responsible, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        contribution.save()
        contribution.questionnaires.set([mommy.make(Questionnaire, is_for_contributors=True)])

        cls.course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        cls.activation = SemesterGradeDownloadActivation.objects.create(semester=cls.course.semester, is_active=True)

    def setUp(self):
        self.course = Course.objects.get(pk=self.course.pk)
        self.activation.refresh_from_db()

    def tearDown(self):
        for course in Course.objects.all():
            for grade_document in course.grade_documents.all():
                grade_document.file.delete()

    def helper_upload_grades(self, course, final_grades):
        upload_files = [('file', 'grades.txt', b"Some content")]

        final = "?final=true" if final_grades else ""
        response = self.app.post(
            "/grades/semester/{}/course/{}/upload{}".format(course.semester.id, course.id, final),
            {"description_en": "Grades", "description_de": "Grades"},
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
        course.staff_approve()
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
        self.helper_check_final_grade_upload(course, course.num_participants + course.contributions.exclude(contributor=None).count())

        # state: published
        course.publish()
        course.save()
        self.helper_check_final_grade_upload(course, 0)

    def test_toggle_no_grades(self):
        course = mommy.make(Course,
            name_en="Toggle",
            vote_start_date=datetime.date.today(),
            state="reviewed",
            participants=[
                UserProfile.objects.get(username="student"),
                UserProfile.objects.get(username="student2"),
                UserProfile.objects.get(username="student3"),
            ],
            voters=[
                UserProfile.objects.get(username="student"),
                UserProfile.objects.get(username="student2"),
            ]
        )
        contribution = Contribution(course=course, contributor=UserProfile.objects.get(username="responsible"), responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        contribution.save()
        contribution.questionnaires.set([mommy.make(Questionnaire, is_for_contributors=True)])

        course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        self.assertFalse(course.gets_no_grade_documents)

        response = self.app.post("/grades/toggle_no_grades", {"course_id": course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        course = Course.objects.get(id=course.id)
        self.assertTrue(course.gets_no_grade_documents)
        # course should get published here
        self.assertEqual(course.state, "published")
        self.assertEqual(len(mail.outbox), course.num_participants + course.contributions.exclude(contributor=None).count())

        response = self.app.post("/grades/toggle_no_grades", {"course_id": course.id}, user="grade_publisher")
        self.assertEqual(response.status_code, 200)
        course = Course.objects.get(id=course.id)
        self.assertFalse(course.gets_no_grade_documents)

    def test_grade_activation(self):
        self.activation.is_active = True
        self.activation.save()

        # upload grade document
        self.helper_upload_grades(self.course, final_grades=False)
        self.assertGreater(self.course.midterm_grade_documents.count(), 0)

        url = "/grades/download/" + str(self.course.midterm_grade_documents.first().id)
        self.get_assert_200(url, "student")  # grades should be downloadable

        self.activation.is_active = False
        self.activation.save()
        self.get_assert_403(url, "student")  # grades should not be downloadable anymore
