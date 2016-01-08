from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from evap.evaluation.models import TextAnswer, UserProfile, Semester, Course

import os
import itertools
import random



class Command(BaseCommand):
    args = ''
    help = 'Anonymizes all the data'

    data_dir = 'anonymize_data'
    firstnames_filename = 'first_names.txt'
    lastnames_filename = 'last_names.txt'
    lorem_ipsum_filename = 'lorem_ipsum.txt'

    ignore_usernames = ['evap', 'student', 'contributor', 'delegate', 'responsible']

    previous_institution_domains = ['hpi.uni-potsdam.de', 'student.hpi.uni-potsdam.de', 'hpi.de', 'student.hpi.de']
    new_institution_domain = ''
    new_external_domain = 'external.com'


    def lorem(self, text, lorem_ipsum):
        word_count = len(text.split(' '))
        return ' '.join(itertools.islice(itertools.cycle(lorem_ipsum), word_count))


    def handle(self, *args, **options):
        print("")
        print("WARNING! This will anonymize all the data in")
        print("the database and cause IRREPARABLE DATA LOSS.")
        if input("Are you sure you want to continue? (yes/no)") != "yes":
            print("Aborting...")
            return
        print("")
        if not settings.DEBUG:
            print("DEBUG is disabled. Are you sure you are not running")
            if input("on a production system and want to continue? (yes/no)") != "yes":
                print("Aborting...")
                return
            print("")

        abs_data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), Command.data_dir)
        first_names = open(os.path.join(abs_data_dir, Command.firstnames_filename)).read().strip().split('\n')
        last_names = open(os.path.join(abs_data_dir, Command.lastnames_filename)).read().strip().split('\n')
        lorem_ipsum = open(os.path.join(abs_data_dir, Command.lorem_ipsum_filename)).read().strip().split(' ')

        try:
            with transaction.atomic():
                print("Replacing text answers with lorem ipsum...")
                for text_answer in TextAnswer.objects.all():
                    text_answer.original_answer = self.lorem(text_answer.original_answer, lorem_ipsum)
                    if text_answer.reviewed_answer:
                        text_answer.reviewed_answer = self.lorem(text_answer.reviewed_answer, lorem_ipsum)
                    text_answer.save()

                print("Generating random usernames...")
                # do this ahead of time to avoid the same name being chosen twice
                user_count = UserProfile.objects.count()
                random_usernames = set()
                while len(random_usernames) != user_count:
                    random_usernames.add((random.choice(first_names), random.choice(last_names)))

                print("Replacing usernames and email addresses with random names...")
                for user, new_username in zip(UserProfile.objects.all(), random_usernames):
                    if user.username in Command.ignore_usernames:
                        continue
                    user.first_name = new_username[0]
                    user.last_name = new_username[1]
                    user.username = (user.first_name + '.' + user.last_name).lower()

                    old_domain = user.email.split('@')[1]
                    is_institution_domain = old_domain in Command.previous_institution_domains
                    new_domain = old_domain if is_institution_domain else Command.new_external_domain

                    user.email = user.username + '@' + new_domain
                    user.save()

                print("Shuffling course data...")
                # do this per semester to avoid problems e.g. with archived semesters
                for semester in Semester.objects.all():
                    shuffled_courses = list(semester.course_set.all())
                    random.shuffle(shuffled_courses)

                    for i, course in enumerate(semester.course_set.all()):
                        course.semester = shuffled_courses[i].semester
                        course.degrees = shuffled_courses[i].degrees
                        course.name_de = shuffled_courses[i].name_de + " " # add a space to avoid name collisions
                        course.name_en = shuffled_courses[i].name_en + " "
                        course.save()

                for course in Course.objects.all():
                    course.name_de = course.name_de[:-1] # remove the space again
                    course.name_en = course.name_en[:-1]

                print("Done.")

        except Exception:
            print("")
            print("An error occurred. No changes were made to the system.")
            print("The stacktrace of the error follows:")
            print("")
            raise
