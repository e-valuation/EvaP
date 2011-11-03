from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from evap.evaluation.models import *

from lxml import etree
from lxml import objectify

import logging
logger = logging.getLogger(__name__)

def nint(v):
    """Nullable int"""
    return int(v) if v is not None else None

class Command(BaseCommand):
    args = '<path to XML file> <semester id|all>'
    help = 'Imports the given semester from the XML file'
    
    question_template_type_map = {"22":"G", "23":"T"}
    
    index_structure = dict(
        answer = [('assessment_id',)],
        assessment = [('course_id',)],
        ccm_to_staff = [('ccm_id',)],
        course = [('evaluation_id',)],
        course_category = [('id',)],
        course_category_mapping = [('course_id',)],
        enrollment = [('course_id',),
                      ('course_id', 'voted')],
        evaluation = [(),
                      ('id',)],
        question_template = [('topic_template_id',)],
        staff = [('id',)],
        student = [('id',)],
        target_audience = [('id',)],
        topic_template = [('questionnaire_template_id',),
                          ('course_category_id','per_person','questionnaire_template_id')],
    )
    
    def store(self, element, *specifiers):
        index = (element.tag, specifiers)
        keys = tuple(nint(getattr(element, s, None)) for s in specifiers)
        self.elements.setdefault(index, dict()).setdefault(keys, list())
        self.elements[index][keys].append(element)
    
    def get(self, tag, **filters):
        specifiers = tuple(sorted(filters.keys()))
        index = (tag, specifiers)
        keys = tuple(nint(filters[s]) for s in specifiers)
        return self.elements[index].get(keys, ())
    
    def get_one(self, *args, **kwargs):
        elements = self.get(*args, **kwargs)
        if len(elements) == 0:
            raise ValueError("No element.")
        elif len(elements) != 1:
            raise ValueError("More than one element.")
        return elements[0]
    
    def get_lecture_types(self, course):
        for ccm in self.get('course_category_mapping', course_id=course.id):
            yield unicode(self.get_one('course_category', id=ccm.course_category_id).name_ge)
    
    def get_participants(self, course):
        for enrollment in self.get('enrollment', course_id=course.id):
            # student --> User
            student = self.get_one('student', id=enrollment.student_id)
            user, created = User.objects.get_or_create(username=unicode(student.loginName))
            yield user
    
    def get_voters(self, course):
        for enrollment in self.get('enrollment', course_id=course.id, voted="1"):
            student = self.get_one('student', id=enrollment.student_id)
            yield User.objects.get(username=unicode(student.loginName))
    
    def get_lecturers(self, course):
        for ccm in self.get('course_category_mapping', course_id=course.id):
            for ccm_to_staff in self.get('ccm_to_staff', ccm_id=ccm.id):
                # staff --> User
                staff = self.get_one('staff', id=ccm_to_staff.staff_id)
                user, created = User.objects.get_or_create(username=unicode(staff.loginName))
                
                # TODO: import name?
                self.staff_cache[int(staff.id)] = user
                
                yield user
    
    def get_questionnaires(self, course, evaluation_id, per_person="0"):
        for ccm in self.get('course_category_mapping', course_id=course.id):
            for topic_template in self.get('topic_template',
                                           course_category_id=ccm.course_category_id,
                                           questionnaire_template_id=evaluation_id,
                                           per_person=per_person):
                yield self.tt_cache[int(topic_template.id)]
    
    def handle(self, *args, **options):
        self.elements = dict()
        self.qt_cache = dict()
        self.tt_cache = dict()
        self.staff_cache = dict()
        
        if len(args) != 2:
            raise Exception("Invalid arguments.")
        
        self.read_xml(args[0])
        if args[1] == "all":
            for evaluation in self.get('evaluation'):
                self.process_semester(str(evaluation.id))
        else:
            self.process_semester(args[1])
    
    def read_xml(self, filename):
        logger.info("Parsing XML file...")
        tree = objectify.parse(filename)
        logger.info("Indexing objects...")
        for element in tree.getroot().iterchildren():
            index_description = self.index_structure.get(element.tag, None)
            if index_description:
                for specifiers in index_description:
                    self.store(element, *specifiers)
    
    def process_semester(self, semester_id):
        logger.info(u"Processing semester %s..." % semester_id)
        with transaction.commit_on_success():
            # evaluation --> Semester
            evaluation = self.get_one('evaluation', id=semester_id)
            semester = Semester.objects.create(name_de=unicode(evaluation.semester),
                                               name_en=unicode(evaluation.semester),
                                               visible=True)
            
            # topic_template --> Questionnaire
            for topic_template in self.get('topic_template', questionnaire_template_id=str(evaluation.id)):
                questionnaire = Questionnaire.objects.create(
                    name_de=u"{0:s} ({1:s})".format(topic_template.name_ge, evaluation.semester),
                    name_en=u"{0:s} ({1:s})".format(topic_template.name_ge, evaluation.semester),
                    obsolete=True)
                
                self.tt_cache[int(topic_template.id)] = questionnaire
                
                # question_template --> Question
                for question_template in sorted(self.get('question_template', topic_template_id=topic_template.id), key=lambda qt: int(qt.idx)):
                    if str(question_template.type) == "21":
                        questionnaire.teaser_de = unicode(question_template.text_ge)
                        questionnaire.teaser_en = unicode(question_template.text_ge)
                        questionnaire.save()
                    else:
                        question = Question.objects.create(
                            questionnaire=questionnaire,
                            text_de=unicode(question_template.text_ge),
                            text_en=unicode(question_template.text_ge),
                            kind=self.question_template_type_map[str(question_template.type)])
                        
                        self.qt_cache[int(question_template.id)] = question
            
            # course --> Course
            for xml_course in self.get('course', evaluation_id=evaluation.id):
                logger.debug(u"Creating course %s", unicode(xml_course.name))
                course = Course.objects.create(
                    semester=semester,
                    name_de=unicode(xml_course.name),
                    name_en=unicode(xml_course.name),
                    vote_start_date=str(xml_course.survey_start_date)[:10],
                    vote_end_date=str(xml_course.survey_start_date)[:10],
                    kind=u",".join(self.get_lecture_types(xml_course)),
                    study=u"Master" if int(xml_course.target_audience_id) == 1 else u"Bachelor",
                    state='published')
                
                course.participants = self.get_participants(xml_course)
                course.voters = self.get_voters(xml_course)
                course.primary_lecturers = self.get_lecturers(xml_course)
                course.general_questions = self.get_questionnaires(xml_course, evaluation.id)
                course.primary_lecturer_questions = self.get_questionnaires(xml_course, evaluation.id, "1")
                course.save()
                
                # answer --> GradeAnswer/TextAnswer
                for assessment in self.get('assessment', course_id=xml_course.id):
                    for answer in self.get('answer', assessment_id=assessment.id):
                        staff_id = nint(getattr(answer, 'staff_id', None))
                        lecturer = self.staff_cache[staff_id] if staff_id is not None else None
                        
                        status = str(answer.revised_status)
                        question = self.qt_cache[int(answer.question_template_id)]
                        
                        if status == "61":
                            GradeAnswer.objects.create(
                                question=question,
                                course=course,
                                lecturer=lecturer,
                                answer=int(answer.response)
                            )
                        else:
                            comment = getattr(answer, 'comment', None)
                            if comment is not None:
                                comment = unicode(comment).strip()
                            
                            if comment:
                                if status == "62":
                                    additional_fields = dict(
                                        hidden=False
                                    )
                                elif status == "63":
                                    additional_fields = dict(
                                        censored_answer=unicode(answer.revised_comment),
                                        hidden=False
                                    )
                                elif status == "64":
                                    additional_fields = dict(
                                        hidden=True
                                    )
                                else:
                                    raise Exception("Invalid XML-file")
                                
                                TextAnswer.objects.create(
                                    question=question,
                                    course=course,
                                    lecturer=lecturer,
                                    original_answer=comment,
                                    checked=True,
                                    **additional_fields
                                )
        
        logger.info("Done.")
