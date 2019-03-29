from datetime import date, timedelta
import os
import itertools
import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from evap.evaluation.models import (Contribution, Course, CourseType, Degree, RatingAnswerCounter, Semester, TextAnswer,
                                    UserProfile)

class Command(BaseCommand):
    args = ''
    help = 'Anonymizes all the data'
    requires_migrations_checks = True

    data_dir = 'anonymize_data'
    firstnames_filename = 'first_names.txt'
    lastnames_filename = 'last_names.txt'
    lorem_ipsum_filename = 'lorem_ipsum.txt'

    ignore_usernames = ['evap', 'student', 'contributor', 'delegate', 'responsible']

    previous_institution_domains = ['hpi.uni-potsdam.de', 'institution.example.com', 'hpi.de', 'student.hpi.de']
    new_institution_domain = settings.INSTITUTION_EMAIL_DOMAINS[0]
    new_external_domain = 'external.example.com'

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write("WARNING! This will anonymize all the data in")
        self.stdout.write("the database and cause IRREPARABLE DATA LOSS.")
        if input("Are you sure you want to continue? (yes/no)") != "yes":
            self.stdout.write("Aborting...")
            return
        self.stdout.write("")
        if not settings.DEBUG:
            self.stdout.write("DEBUG is disabled. Are you sure you are not running")
            if input("on a production system and want to continue? (yes/no)") != "yes":
                self.stdout.write("Aborting...")
                return
            self.stdout.write("")

        self.anonymize_data()

    def anonymize_data(self):
        abs_data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), Command.data_dir)

        # load placeholders
        with open(os.path.join(abs_data_dir, Command.firstnames_filename)) as f:
            first_names = f.read().strip().split('\n')
        with open(os.path.join(abs_data_dir, Command.lastnames_filename)) as f:
            last_names = f.read().strip().split('\n')
        with open(os.path.join(abs_data_dir, Command.lorem_ipsum_filename)) as f:
            lorem_ipsum = f.read().strip().split(' ')

        try:
            with transaction.atomic():
                self.anonymize_email_templates()
                self.anonymize_users(first_names, last_names)
                self.anonymize_courses()
                self.anonymize_evaluations()
                self.anonymize_questionnaires(lorem_ipsum)

                self.stdout.write("Done.")

        except Exception:
            self.stdout.write("")
            self.stdout.write("An error occurred. No changes were made to the system.")
            self.stdout.write("The stacktrace of the error follows:")
            self.stdout.write("")
            raise

    def anonymize_email_templates(self):
        self.stdout.write("REMINDER: The email templates could still contain sensitive contact information...")

    # Replaces names, usernames, email addresses, login keys and valid until dates with fake ones
    def anonymize_users(self, first_names, last_names):
        user_profiles = UserProfile.objects.all()

        # Generate as many fake usernames as real ones exist. Use the provided first/last names for that
        self.stdout.write("Generating fake usernames...")
        fake_usernames = set()

        if len(first_names) * len(last_names) < len(user_profiles) * 1.5:
            self.stdout.write("Warning: There are few example names compared to all that real data to be anonymized. "
                + "Consider adding more data to the first_names.txt and last_names.txt files in the anonymize_data "
                + "folder.")

        while len(fake_usernames) < len(user_profiles):
            fake_usernames.add(
                (random.choice(first_names), random.choice(last_names)))

        for i, user in enumerate(user_profiles):
            # Give users unique temporary names to counter identity errors due to the names being unique
            if user.username in Command.ignore_usernames:
                continue
            user.username = f"<User #{i}>"
            user.save()

        # Actually replace all the real user data
        self.stdout.write("Replacing usernames, email addresses and login keys with fake ones...")
        for user, name in zip(user_profiles, fake_usernames):
            if user.username in Command.ignore_usernames:
                continue
            user.first_name = name[0]
            user.last_name = name[1]
            user.username = (user.first_name + '.' + user.last_name).lower()

            if user.email:
                old_domain = user.email.split('@')[1]
                is_institution_domain = old_domain in Command.previous_institution_domains
                new_domain = Command.new_institution_domain if is_institution_domain else Command.new_external_domain
                user.email = user.username + '@' + new_domain

            if user.login_key is not None:
                # Create a new login key
                user.login_key = None
                user.valid_until = None
                user.ensure_valid_login_key()
                # Invalidate some keys
                user.valid_until = date.today() + random.choice([1, -1]) * timedelta(365 * 100)

            user.save()

    def anonymize_courses(self):
        all_degrees = list(Degree.objects.all())
        all_course_types = CourseType.objects.all()

        # Randomize the degrees
        self.stdout.write("Randomizing degrees...")
        for course in Course.objects.all():
            degrees = random.sample(all_degrees, course.degrees.count())
            course.degrees.set(degrees)

        # Randomize course types
        self.stdout.write("Randomizing course types...")
        for course in Course.objects.all():
            course.type = random.choice(all_course_types)
            course.save()

        # Randomize names
        for semester in Semester.objects.all():
            courses = list(semester.courses.all())
            random.shuffle(courses)
            public_courses = [course for course in courses if not course.is_private]

            self.stdout.write(f"Anonymizing {len(courses)} courses of semester {semester}...")

            # Shuffle public courses' names in order to decouple them from the results.
            # Also, assign public courses' names to private ones as their names may be confidential.
            self.stdout.write("Shuffling course names...")
            public_names = list(set(map(lambda c: (c.name_de, c.name_en), public_courses)))
            random.shuffle(public_names)

            for i, course in enumerate(courses):
                # Give courses unique temporary names to counter identity errors due to the names being unique
                course.name_de = f"<Veranstaltung #{i}>"
                course.name_en = f"<Course #{i}>"
                course.save()

            for i, course in enumerate(courses):
                if public_names:
                    name = public_names.pop()
                    course.name_de = name[0]
                    course.name_en = name[1]
                else:
                    course.name_de = f"Veranstaltung #{i + 1}"
                    course.name_en = f"Course #{i + 1}"
                course.save()

    def anonymize_evaluations(self):
        for semester in Semester.objects.all():
            evaluations = list(semester.evaluations.all())
            random.shuffle(evaluations)
            self.stdout.write(f"Anonymizing {len(evaluations)} evaluations of semester {semester}...")

            self.stdout.write("Shuffling evaluation names...")
            named_evaluations = (evaluation for evaluation in evaluations if evaluation.name_de and evaluation.name_en)
            names = list(set(map(lambda c: (c.name_de, c.name_en), named_evaluations)))
            random.shuffle(names)

            for i, evaluation in enumerate(evaluations):
                # Give evaluations unique temporary names to counter identity errors due to the names being unique
                if evaluation.name_de:
                    evaluation.name_de = f"<Evaluierung #{i}>"
                if evaluation.name_en:
                    evaluation.name_en = f"<Evaluation #{i}>"
                evaluation.save()

            for i, evaluation in enumerate(evaluations):
                if not evaluation.name_de and not evaluation.name_en:
                    continue
                if names:
                    name = names.pop()
                    evaluation.name_de = name[0]
                    evaluation.name_en = name[1]
                else:
                    evaluation.name_de = f"Evaluierung #{i + 1}"
                    evaluation.name_en = f"Evaluation #{i + 1}"
                evaluation.save()

    def anonymize_questionnaires(self, lorem_ipsum):
        # questionnaires = Questionnaire.objects.all()

        self.stdout.write("REMINDER: You still need to randomize the questionnaire names...")
        self.stdout.write("REMINDER: You still need to randomize the questionnaire questions...")

        self.stdout.write("Replacing text answers with fake ones...")
        for text_answer in TextAnswer.objects.all():
            text_answer.answer = self.lorem(text_answer.answer, lorem_ipsum)
            if text_answer.original_answer:
                text_answer.original_answer = self.lorem(text_answer.original_answer, lorem_ipsum)
            text_answer.save()

    # Returns a string with the same number of lorem ipsum words as the given text
    @staticmethod
    def lorem(text, lorem_ipsum):
        word_count = len(text.split(' '))
        return ' '.join(itertools.islice(itertools.cycle(lorem_ipsum), word_count))
