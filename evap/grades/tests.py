﻿from django_webtest import WebTest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group

from model_mommy import mommy
import tempfile
import datetime

from evap.evaluation.models import UserProfile, Course, Questionnaire, Contribution


class GradeUploadTests(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="grade_publisher", groups=[Group.objects.get(name="Grade publisher")])
        mommy.make(UserProfile, username="student", email="student@student.hpi.de")
        mommy.make(UserProfile, username="student2", email="student2@student.hpi.de")
        mommy.make(UserProfile, username="student3", email="student3@student.hpi.de")
        mommy.make(UserProfile, username="responsible", email="responsible@hpi.de")

        course = mommy.make(Course,
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
        contribution = Contribution(course=course, contributor=UserProfile.objects.get(username="responsible"), responsible=True)
        contribution.save()
        contribution.questionnaires = [mommy.make(Questionnaire, is_for_contributors=True)]

        course.general_contribution.questionnaires = [mommy.make(Questionnaire)]

    def tearDown(self):
        for course in Course.objects.all():
            for grade_document in course.grade_documents.all():
                grade_document.file.delete()

    def get_assert_200(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def get_submit_assert_302(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit("")
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def helper_upload_grades(self, course, final_grades):
        with tempfile.SpooledTemporaryFile() as f:
            f.write(b"Grades")
            f.seek(0)
            upload_files = [
                ('file', 'grades.txt', f.read())
            ]

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
        course = Course.objects.get(name_en="Test")
        self.assertEqual(course.midterm_grade_documents.count(), 0)

        response = self.helper_upload_grades(course, final_grades=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Successfully", response)
        self.assertEqual(course.midterm_grade_documents.count(), 1)
        self.assertEqual(len(mail.outbox), course.num_participants)

    def test_upload_final_grades(self):
        course = Course.objects.get(name_en="Test")
        self.assertEqual(course.final_grade_documents.count(), 0)

        # state: new
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: prepared
        course.ready_for_editors()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: editorApproved
        course.editor_approve()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: approved
        course.staff_approve()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: inEvaluation
        course.evaluation_begin()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: evaluated
        course.evaluation_end()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

        # state: reviewed
        course.review_finished()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants + course.contributions.exclude(contributor=None).count())

        # state: published
        course.publish()
        course.save()
        self.helper_check_final_grade_upload(course, course.num_participants)

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
        contribution = Contribution(course=course, contributor=UserProfile.objects.get(username="responsible"), responsible=True)
        contribution.save()
        contribution.questionnaires = [mommy.make(Questionnaire, is_for_contributors=True)]

        course.general_contribution.questionnaires = [mommy.make(Questionnaire)]

        toggle_url = "/grades/semester/"+str(course.semester.id)+"/course/"+str(course.id)+"/togglenogrades"

        self.assertFalse(course.gets_no_grade_documents)

        self.get_submit_assert_302(toggle_url, "grade_publisher")
        course = Course.objects.get(id=course.id)
        self.assertTrue(course.gets_no_grade_documents)
        # course should get published here
        self.assertEqual(course.state, "published")
        self.assertEqual(len(mail.outbox), course.num_participants + course.contributions.exclude(contributor=None).count())

        self.get_submit_assert_302(toggle_url, "grade_publisher")
        course = Course.objects.get(id=course.id)
        self.assertFalse(course.gets_no_grade_documents)
