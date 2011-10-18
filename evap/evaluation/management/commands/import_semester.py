from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from evap.evaluation.models import *

from lxml import etree

class Command(BaseCommand):
    args = '<path to XML file> <semester_id>'
    help = 'Imports the given semester from the XML file'
    
    question_template_type_map = {"22":"G", "23":"T"}
    
    def get_study_type(self, ta_id):
        return self.tree.find("/target_audience[id='{0:s}']/name".format(ta_id)).text

    def get_lecture_types(self, course):
        course_id = course.find("id").text
        for cc_id in self.tree.findall("/course_category_mapping[course_id='{0:s}']/course_category_id".format(course_id)):
            yield self.tree.find("/course_category[id='{0:s}']/name_ge".format(cc_id.text)).text.encode('utf-8')

    def get_participants(self, course):
        course_id = course.find("id").text
        for enrollment in self.tree.findall("/enrollment[course_id='{0:s}']".format(course_id)):
            # student --> User
            student = self.tree.find("/student[id='{0:s}']".format(enrollment.find("student_id").text))
            user, created = User.objects.get_or_create(username=student.find("loginName").text)
            
            self.student_cache[enrollment.find("student_id").text] = user
            
            yield user
        
    def get_voters(self, course):
        course_id = course.find("id").text
        for enrollment in self.tree.findall("/enrollment[course_id='{0:s}'][voted='1']".format(course_id)):
            # student --> User
            student = self.tree.find("/student[id='{0:s}']".format(enrollment.find("student_id").text))
            user, created = User.objects.get_or_create(username=student.find("loginName").text)
            
            self.student_cache[enrollment.find("student_id").text] = user
            
            yield user

    def get_lecturers(self, course):
        course_id = course.find("id").text
        for ccm_id in self.tree.findall("/course_category_mapping[course_id='{0:s}']/id".format(course_id)):
            for staff_id in self.tree.findall("/ccm_to_staff[ccm_id='{0:s}']/staff_id".format(ccm_id.text)):
                # staff --> User
                staff = self.tree.find("/staff[id='{0:s}']".format(staff_id.text))
                user, created = User.objects.get_or_create(username=staff.find("loginName").text)
                
                #TODO: import name
                self.staff_cache[staff_id.text] = user
                
                yield user
    
    def get_questionnaires(self, course, evaluation_id, per_person="0"):
        course_id = course.find("id").text
        for cc_id in self.tree.findall("/course_category_mapping[course_id='{0:s}']/course_category_id".format(course_id)):
            for tt_id in self.tree.findall("/topic_template[course_category_id='{0:s}'][questionnaire_template_id='{1:s}'][per_person='{2:s}']/id".format(cc_id.text, evaluation_id, per_person)):
                yield self.tt_cache[tt_id.text]
    
    def handle(self, *args, **options):
        self.tree = etree.ElementTree()
        self.tree.parse(args[0])
        
        with transaction.commit_on_success():
            # evaluation --> Semester
            evaluation = self.tree.find("/evaluation[id='{0:s}']".format(str(args[1])))
            evaluation_id = evaluation.find("id").text
            semester = Semester.objects.create(name_de=evaluation.find("semester").text)
            
            # create caches
            self.qt_cache = {}
            self.staff_cache = {}
            self.student_cache = {}
            self.tt_cache = {}
            
            # topic_template --> Questionnaire
            for topic_template in self.tree.findall("/topic_template[questionnaire_template_id='{0:s}']".format(evaluation_id)):
                questionnaire = Questionnaire.objects.create(
                    name_de="{0:s} ({1:s})".format(topic_template.find("name_ge").text, evaluation.find("semester").text),
                    name_en="{0:s} ({1:s})".format(topic_template.find("name_ge").text, evaluation.find("semester").text))
                
                self.tt_cache[topic_template.find("id").text] = questionnaire
                
                # question_template --> Question
                for question_template in sorted(self.tree.findall("/question_template[topic_template_id='{0:s}']".format(topic_template.find('id').text)), key=lambda qt: int(qt.find("idx").text)):
                    if question_template.find("type").text == "21":
                        questionnaire.description_de = question_template.find("text_ge").text
                        questionnaire.save()
                    else:
                        question = Question.objects.create(
                            questionnaire=questionnaire,
                            text_de=question_template.find("text_ge").text,
                            kind=self.question_template_type_map[question_template.find("type").text])
                        
                        self.qt_cache[question_template.find("id").text] = question
            
            # course --> Course
            for xml_course in self.tree.findall("/course[evaluation_id='{0:s}']".format(evaluation_id)):
                course = Course.objects.create(
                    semester=semester,
                    name_de=xml_course.find("name").text,
                    name_en=xml_course.find("name").text,
                    vote_start_date=xml_course.find("survey_start_date").text[:10],
                    vote_end_date=xml_course.find("survey_end_date").text[:10],
                    visible=True,
                    kind=",".join(self.get_lecture_types(xml_course)))
                
                course.participants = self.get_participants(xml_course)
                course.voters = self.get_voters(xml_course)
                course.primary_lecturers = self.get_lecturers(xml_course)
                course.general_questions = self.get_questionnaires(xml_course, evaluation_id)
                course.primary_lecturer_questions = self.get_questionnaires(xml_course, evaluation_id, "1")
                course.save()
                
                # answer --> GradeAnswer/TextAnswer
                for assessment_id in self.tree.findall("/assessment[course_id='{0:s}']/id".format(xml_course.find("id").text)):
                    for answer in self.tree.findall("/answer[assessment_id='{0:s}']".format(assessment_id.text)):
                        staff_id = answer.find('staff_id')
                        lecturer = self.staff_cache[staff_id.text] if staff_id is not None else None
                        
                        # really create answers
                        status = answer.find("revised_status").text
                        if status == "61":
                            GradeAnswer.objects.create(
                                question=self.qt_cache[answer.find("question_template_id").text],
                                course=course,
                                lecturer=lecturer,
                                answer=int(answer.find("response").text))
                        else:
                            comment = answer.find('comment')
                            if comment is not None:
                                comment = comment.text.strip() if comment.text is not None else None
                            
                            if comment:
                                if status == "62":
                                    TextAnswer.objects.create(
                                        question=self.qt_cache[answer.find("question_template_id").text],
                                        course=course,
                                        lecturer=lecturer,
                                        original_answer=comment,
                                        checked=True,
                                        hidden=False
                                    )
                                elif status == "63":
                                    TextAnswer.objects.create(
                                        question=self.qt_cache[answer.find("question_template_id").text],
                                        course=course,
                                        lecturer=lecturer,
                                        original_answer=comment,
                                        censored_answer=answer.find("revised_comment").text,
                                        checked=True,
                                        hidden=False
                                    )
                                elif status == "64":
                                    TextAnswer.objects.create(
                                        question=self.qt_cache[answer.find("question_template_id").text],
                                        course=course,
                                        lecturer=lecturer,
                                        original_answer=comment,
                                        checked=True,
                                        hidden=True
                                    )
                                else:
                                    raise Exception("Invalid XML-file")
