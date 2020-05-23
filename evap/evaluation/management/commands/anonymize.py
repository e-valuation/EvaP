from datetime import date, timedelta
import os
import itertools
from math import floor
import random

from collections import defaultdict
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.serializers.base import ProgressBar
from django.db import transaction

from evap.evaluation.models import (CHOICES, Contribution, Course, CourseType, Degree,
        NO_ANSWER, RatingAnswerCounter, Semester, TextAnswer, UserProfile)


class Command(BaseCommand):
    args = ''
    help = 'Anonymizes all the data'
    requires_migrations_checks = True

    data_dir = 'anonymize_data'
    firstnames_filename = 'first_names.txt'
    lastnames_filename = 'last_names.txt'
    lorem_ipsum_filename = 'lorem_ipsum.txt'

    ignore_emails = ['evap', 'student', 'contributor', 'delegate', 'responsible']

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
        with open(os.path.join(abs_data_dir, Command.firstnames_filename)) as firstnames_file:
            first_names = firstnames_file.read().strip().split('\n')
        with open(os.path.join(abs_data_dir, Command.lastnames_filename)) as lastnames_file:
            last_names = lastnames_file.read().strip().split('\n')
        with open(os.path.join(abs_data_dir, Command.lorem_ipsum_filename)) as lorem_ipsum_file:
            lorem_ipsum = lorem_ipsum_file.read().strip().split(' ')

        try:
            with transaction.atomic():
                self.anonymize_email_templates()
                self.anonymize_users(first_names, last_names)
                self.anonymize_courses()
                self.anonymize_evaluations()
                self.anonymize_questionnaires()
                self.anonymize_answers(lorem_ipsum)

                self.stdout.write("")
                self.stdout.write("Done.")

        except Exception:
            self.stdout.write("")
            self.stdout.write("An error occurred. No changes were made to the system.")
            self.stdout.write("The stacktrace of the error follows:")
            self.stdout.write("")
            raise

    def anonymize_email_templates(self):
        self.stdout.write("REMINDER: The email templates could still contain sensitive contact information...")

    # Replaces names, email addresses, login keys and valid until dates with fake ones
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
            fake_usernames.add((random.choice(first_names), random.choice(last_names)))  # nosec

        for i, user in enumerate(user_profiles):
            # Give users unique temporary emails to counter identity errors due to the emails being unique
            if user.email:
                if user.email.split('@')[0] in Command.ignore_emails:
                    continue
                user.email = f"<User.{i}>@{user.email.split('@')[1]}"
                user.save()

        # Actually replace all the real user data
        self.stdout.write("Replacing email addresses and login keys with fake ones...")
        for user, name in zip(user_profiles, fake_usernames):
            if user.email and user.email.split('@')[0] in Command.ignore_emails:
                continue
            user.first_name = name[0]
            user.last_name = name[1]

            if user.email:
                old_domain = user.email.split('@')[1]
                is_institution_domain = old_domain in Command.previous_institution_domains
                new_domain = Command.new_institution_domain if is_institution_domain else Command.new_external_domain
                user.email = (user.first_name + '.' + user.last_name).lower() + '@' + new_domain

            if user.login_key is not None:
                # Create a new login key
                user.login_key = None
                user.valid_until = None
                user.ensure_valid_login_key()
                # Invalidate some keys
                user.valid_until = date.today() + random.choice([1, -1]) * timedelta(365 * 100)  # nosec

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
            course.type = random.choice(all_course_types)  # nosec
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

    def anonymize_questionnaires(self):
        self.stdout.write("REMINDER: You still need to randomize the questionnaire names...")
        self.stdout.write("REMINDER: You still need to randomize the questionnaire questions...")

    def anonymize_answers(self, lorem_ipsum):
        # This method is very mathematical and has a lot of "one new variable per line" code, but we think it's okay.
        # pylint: disable=too-many-locals
        self.stdout.write("Replacing text answers with fake ones...")
        for text_answer in TextAnswer.objects.all():
            text_answer.answer = self.lorem(text_answer.answer, lorem_ipsum)
            if text_answer.original_answer:
                text_answer.original_answer = self.lorem(text_answer.original_answer, lorem_ipsum)
            text_answer.save()

        self.stdout.write("Shuffling rating answer counter counts...")

        contributions = Contribution.objects.all().prefetch_related("ratinganswercounter_set__question")
        try:
            self.stdout.ending = ""
            progress_bar = ProgressBar(self.stdout, contributions.count())
            for contribution_counter, contribution in enumerate(contributions):
                progress_bar.update(contribution_counter + 1)

                counters_per_question = defaultdict(list)
                for counter in contribution.ratinganswercounter_set.all():
                    counters_per_question[counter.question].append(counter)

                for question, counters in counters_per_question.items():
                    original_sum = sum(counter.count for counter in counters)

                    missing_values = set(CHOICES[question.type].values).difference(set(c.answer for c in counters))
                    missing_values.discard(NO_ANSWER)  # don't add NO_ANSWER counter if it didn't exist before
                    for value in missing_values:
                        counters.append(RatingAnswerCounter(question=question, contribution=contribution, answer=value, count=0))

                    generated_counts = [random.random() for c in counters]  # nosec
                    generated_sum = sum(generated_counts)
                    generated_counts = [floor(count / generated_sum * original_sum) for count in generated_counts]

                    to_add = original_sum - sum(generated_counts)
                    index = random.randint(0, len(generated_counts) - 1)  # nosec
                    generated_counts[index] += to_add

                    for counter, generated_count in zip(counters, generated_counts):
                        assert generated_count >= 0
                        counter.count = generated_count

                        if counter.count:
                            counter.save()
                        elif counter.id:
                            counter.delete()

                    assert original_sum == sum(counter.count for counter in counters)
        finally:
            self.stdout.ending = "\n"

    # Returns a string with the same number of lorem ipsum words as the given text
    @staticmethod
    def lorem(text, lorem_ipsum):
        word_count = len(text.split(' '))
        return ' '.join(itertools.islice(itertools.cycle(lorem_ipsum), word_count))
