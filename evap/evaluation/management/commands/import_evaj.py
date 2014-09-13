from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from evap.evaluation.models import Contribution, Course, LikertAnswer, Question, \
                                   Questionnaire, Semester, TextAnswer, UserProfile

from datetime import datetime
from lxml import objectify

import logging
logger = logging.getLogger(__name__)


def nint(v):
    """Nullable int"""
    return int(v) if v is not None else None


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()


class NotOneException(Exception):
    pass


class Command(BaseCommand):
    args = "<path to XML file> [evaluation_id ...]"
    help = "Imports one or all semesters from an EvaJ XML dump."

    question_template_type_map = {"22": "L", "23": "T"}

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
                          ('course_category_id', 'per_person', 'questionnaire_template_id')],
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
            raise NotOneException("No %r element for %r." % (args, kwargs))
        elif len(elements) != 1:
            raise NotOneException("More than one %r element for %r." % (args, kwargs))
        return elements[0]

    def user_from_db(self, username):
        u = unicode(username)[:30]
        user, _ = User.objects.get_or_create(username__iexact=u, defaults=dict(username=u))
        return user

    def get_lecture_types(self, course):
        for ccm in self.get('course_category_mapping', course_id=course.id):
            yield unicode(self.get_one('course_category', id=ccm.course_category_id).name_ge)

    def get_participants(self, course):
        for enrollment in self.get('enrollment', course_id=course.id):
            # student --> User
            student = self.get_one('student', id=enrollment.student_id)
            yield self.user_from_db(student.loginName)

    def get_voters(self, course):
        for enrollment in self.get('enrollment', course_id=course.id, voted=1):
            student = self.get_one('student', id=enrollment.student_id)
            yield self.user_from_db(student.loginName)

    def get_contributors_with_questionnaires(self, course):
        for ccm in self.get('course_category_mapping', course_id=course.id):
            for ccm_to_staff in self.get('ccm_to_staff', ccm_id=ccm.id):
                # staff --> User
                staff = self.get_one('staff', id=ccm_to_staff.staff_id)
                user = self.user_from_db(staff.loginName)

                # import name
                profile = UserProfile.get_for_user(user)
                name_parts = unicode(staff.name).split()
                if name_parts[0].startswith("Dr"):
                    user.last_name = " ".join(name_parts[1:])
                    profile.title = name_parts[0]
                elif name_parts[0] == "Prof.":
                    user.last_name = " ".join(name_parts[2:])
                    profile.title = " ".join(name_parts[:2])
                elif name_parts[0].startswith("Prof"):
                    user.last_name = " ".join(name_parts[1:])
                    profile.title = name_parts[0]
                elif len(name_parts) == 2:
                    user.first_name = name_parts[0]
                    user.last_name = name_parts[1]
                user.save()
                profile.save()

                # TODO: import name?
                self.staff_cache[int(staff.id)] = user
                try:
                    topic_template = self.get_one('topic_template',
                                                  course_category_id=ccm.course_category_id,
                                                  questionnaire_template_id=course.evaluation_id,
                                                  per_person="1")

                    questionnaire = self.questionnaire_cache[int(topic_template.id)]

                    yield user, questionnaire
                except NotOneException:
                    logger.warn("Skipping questionnaire for contributor %r in course %r.", user, course.name)

    def get_questionnaires(self, course, evaluation_id, per_person="0"):
        questionnaire_template_id = self.get_one('evaluation', id=evaluation_id).questionnaire_template_id
        for ccm in self.get('course_category_mapping', course_id=course.id):
            for topic_template in self.get('topic_template',
                                           course_category_id=ccm.course_category_id,
                                           questionnaire_template_id=questionnaire_template_id,
                                           per_person=per_person):
                yield self.questionnaire_cache[int(topic_template.id)]

    def handle(self, *args, **options):
        self.elements = dict()
        self.staff_cache = dict()

        if len(args) < 1:
            raise CommandError("Not enough arguments given.")

        self.read_xml(args[0])

        if len(args) < 2:
            ids = [str(evaluation.id) for evaluation in self.get('evaluation')]
            raise CommandError("No evaluation IDs given. Valid IDs are: %s" % ", ".join(ids))

        for arg in args[1:]:
            self.process_semester(arg)

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
        self.questionnaire_cache = dict() # topic template id -> Questionnaire
        self.question_cache = dict()  # question template id -> Question

        # evaluation --> Semester
        evaluation = self.get_one('evaluation', id=semester_id)
        logger.info(u"Processing semester '%s'...", evaluation.semester)
        semester = Semester.objects.create(name_de=unicode(evaluation.semester),
                                           name_en=unicode(evaluation.semester))
        # hack: use default start date to get the ordering right
        semester.created_at = parse_date(str(evaluation.default_start_date))
        semester.save()

        # topic_template --> Questionnaire
        for topic_template in self.get('topic_template', questionnaire_template_id=evaluation.questionnaire_template_id):
            try:
                with transaction.commit_on_success():
                    questionnaire = Questionnaire.objects.create(
                        # hack: make names unique by adding the original IDs
                        name_de=u"{0:s} ({1:s})".format(topic_template.name_ge, topic_template.id),
                        name_en=u"{0:s} ({1:s})".format(topic_template.name_ge, topic_template.id),
                        description=u"Imported from EvaJ, Semester %s" % evaluation.semester,
                        obsolete=True)

                    self.questionnaire_cache[int(topic_template.id)] = questionnaire

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
                            self.question_cache[int(question_template.id)] = question
            except Exception:
                logger.exception(u"An exception occurred while trying to import questionnaire '%s'!", topic_template.name_ge)

        courses = self.get('course', evaluation_id=evaluation.id)
        course_count = 0

        # course --> Course
        for xml_course in courses:
            logger.debug(u"Creating course %s (id=%d evaluation=%d)", unicode(xml_course.name), xml_course.id, xml_course.evaluation_id)
            try:
                with transaction.commit_on_success():
                    course = Course.objects.create(
                        semester=semester,
                        name_de=unicode(xml_course.name),
                        name_en=unicode(xml_course.name),
                        vote_start_date=parse_date(str(xml_course.survey_start_date)),
                        vote_end_date=parse_date(str(xml_course.survey_start_date)),
                        kind=u",".join(self.get_lecture_types(xml_course)),
                        degree=u"Master" if int(xml_course.target_audience_id) == 1 else u"Bachelor",
                        state='published')

                    course.participants = self.get_participants(xml_course)
                    course.voters = self.get_voters(xml_course)
                    course.save()

                    # general quesitonnaires
                    Contribution.objects.get(course=course, contributor=None).questionnaires = self.get_questionnaires(xml_course, evaluation.id)

                    # contributor questionnaires
                    for contributor, questionnaire in self.get_contributors_with_questionnaires(xml_course):
                        contribution, _ = Contribution.objects.get_or_create(course=course, contributor=contributor)
                        contribution.questionnaires.add(questionnaire)

                    # answer --> LikertAnswer/TextAnswer
                    for assessment in self.get('assessment', course_id=xml_course.id):
                        for answer in self.get('answer', assessment_id=assessment.id):
                            staff_id = nint(getattr(answer, 'staff_id', None))
                            contributor = self.staff_cache[staff_id] if staff_id is not None else None
                            contribution = course.contributions.get(contributor=contributor)

                            status = str(answer.revised_status)
                            try:
                                question = self.question_cache[int(answer.question_template_id)]
                            except (AttributeError, KeyError):
                                logger.warn("No question found for answer %r", answer.id)
                                continue

                            if status == "61":
                                LikertAnswer.objects.create(
                                    contribution=contribution,
                                    question=question,
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
                                            reviewed_answer=unicode(answer.revised_comment),
                                            hidden=False
                                        )
                                    elif status == "64":
                                        additional_fields = dict(
                                            hidden=True
                                        )
                                    else:
                                        raise Exception("Invalid XML-file")

                                    TextAnswer.objects.create(
                                        contribution=contribution,
                                        question=question,
                                        original_answer=comment,
                                        checked=True,
                                        **additional_fields
                                    )

                course_count += 1
            except Exception:
                logger.exception(u"An exception occurred while trying to import course '%s'!", xml_course.name)

        logger.info("Done, %d of %d courses imported.", course_count, len(courses))
