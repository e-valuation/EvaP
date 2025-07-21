from typing import Any

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    invisibility_of_element_located,
    visibility_of_element_located,
)

from evap.evaluation.models import Course, CourseType, Evaluation, Program, Semester, UserProfile
from evap.evaluation.tests.tools import LiveServerTest


class ResultsIndexLiveTests(LiveServerTest):
    def setUp(self):
        super().setUp()

        def make_winter_semester(year: int) -> Semester:
            return baker.make(
                Semester,
                name_de=f"Wintersemester {year}/{year + 1}",
                name_en=f"Winter term {year}/{year + 1}",
                short_name_de=f"WS {year % 1000}/{year % 1000 + 1}",
                short_name_en=f"WT {year % 1000}/{year % 1000 + 1}",
            )

        def make_summer_semester(year: int) -> Semester:
            return baker.make(
                Semester,
                name_de=f"Sommersemester {year}",
                name_en=f"Summer term {year}",
                short_name_de=f"SS {year % 1000}",
                short_name_en=f"ST {year % 1000}",
            )

        semesters = [
            make_summer_semester(2014),
            make_winter_semester(2013),
            make_summer_semester(2013),
        ]
        programs = {
            "ba-a": baker.make(Program, name_de="Bachelor A", name_en="Bachelor A"),
            "ma-a": baker.make(Program, name_de="Master A", name_en="Master A"),
            "ma-b": baker.make(Program, name_de="Master B", name_en="Master B"),
        }
        course_types = {
            "l": baker.make(CourseType, name_de="Vorlesung", name_en="Lecture"),
            "s": baker.make(CourseType, name_de="Seminar", name_en="Seminar"),
        }

        def make_responsible(title: str, first_name: str, last_name: str) -> UserProfile:
            return baker.make(
                UserProfile,
                title=title,
                first_name_given=first_name,
                last_name=last_name,
            )

        responsibles = {
            "responsible": make_responsible("Prof. Dr.", "", "responsible"),
            "goldwasser": make_responsible("Dr.", "Clara", "Goldwasser"),
            "kuchenbuch": make_responsible("Dr.", "Tony", "Kuchenbuch"),
        }

        def make_course(name, semester, course_type_name, program_names, responsible_names):
            return baker.make(
                Course,
                semester=semesters[semester],
                name_de=f"Veranstaltung {name}",
                name_en=f"Course {name}",
                type=course_types[course_type_name],
                programs={programs[program_name] for program_name in program_names},
                responsibles={responsibles[responsible_name] for responsible_name in responsible_names},
            )

        courses = {
            "a-0": make_course("A", 0, "l", {"ba-a"}, {"responsible"}),
            "a-1": make_course("A", 1, "l", {"ba-a"}, {"responsible"}),
            "a-2": make_course("A", 2, "l", {"ba-a"}, {"responsible"}),
            "c": make_course("C", 0, "s", {"ba-a", "ma-a"}, {"goldwasser"}),
            "d": make_course("D", 0, "l", {"ma-a", "ma-b"}, {"kuchenbuch", "goldwasser"}),
            "e": make_course("E", 2, "s", {"ma-a"}, {"kuchenbuch"}),
        }

        def make_evaluation(course_name: str, participant_count: int, voter_count: int, **attrs: Any) -> None:
            baker.make(
                Evaluation,
                state=Evaluation.State.PUBLISHED,
                course=courses[course_name],
                _participant_count=participant_count,
                _voter_count=voter_count,
                **attrs,
            )

        make_evaluation("a-0", 100, 80)
        make_evaluation("a-1", 100, 85)
        make_evaluation("a-2", 100, 80)
        make_evaluation("a-2", 100, 75, name_de="Klausur", name_en="Exam")
        make_evaluation("c", 20, 15)
        make_evaluation("d", 50, 45)
        make_evaluation("e", 5, 5)

        self.url = self.live_server_url + reverse("results:index")

    def assertRowsVisible(self, *rows: tuple[str, str]):
        items = tuple(
            (
                row.find_element(By.CLASS_NAME, "evaluation-name").text,
                row.find_element(By.CLASS_NAME, "semester-short-name").text,
            )
            for row in self.selenium.find_elements(By.CLASS_NAME, "heading-row")
        )
        self.assertEqual(items, rows)

    def test_results_initially_sorted_by_evaluation_and_semester(self):
        self.selenium.get(self.url)
        self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button"))).click()

        self.assertRowsVisible(
            ("Course A", "ST 14"),
            ("Course A", "WT 13/14"),
            ("Course A", "ST 13"),
            ("Course C", "ST 14"),
            ("Course D", "ST 14"),
            ("Course E", "ST 13"),
        )

    def test_results_filter_with_search_input(self):
        self.selenium.get(self.url)
        self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button"))).click()

        self.selenium.find_element(By.CSS_SELECTOR, "input[name=search]").send_keys("Exam")
        self.wait.until(invisibility_of_element_located((By.XPATH, "//span[contains(text(),'Course C')]")))

        self.assertRowsVisible(("Course A", "ST 13"))

    def test_results_filter_with_program_checkbox(self):
        self.selenium.get(self.url)
        self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button"))).click()

        self.selenium.find_element(By.CSS_SELECTOR, "input[name=program][data-filter='Bachelor A']").click()
        self.assertRowsVisible(
            ("Course A", "ST 14"), ("Course A", "WT 13/14"), ("Course A", "ST 13"), ("Course C", "ST 14")
        )

    def test_results_filter_with_course_type_checkbox(self):
        self.selenium.get(self.url)
        self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button"))).click()

        self.selenium.find_element(By.CSS_SELECTOR, "input[name=courseType][data-filter='Seminar']").click()
        self.assertRowsVisible(("Course C", "ST 14"), ("Course E", "ST 13"))

    def test_results_filter_with_semester_checkbox(self):
        self.selenium.get(self.url)
        self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button"))).click()

        self.selenium.find_element(By.CSS_SELECTOR, "input[name=semester][data-filter='ST 13']").click()
        self.assertRowsVisible(("Course A", "ST 13"), ("Course E", "ST 13"))

    def test_results_clear_filter(self):
        self.selenium.get(self.url)
        reset_button = self.wait.until(visibility_of_element_located((By.CLASS_NAME, "reset-button")))
        reset_button.click()

        search_input = self.selenium.find_element(By.CSS_SELECTOR, "input[name=search]")
        program_checkbox = self.selenium.find_element(By.CSS_SELECTOR, "input[name=program][data-filter='Bachelor A']")
        course_type_checkbox = self.selenium.find_element(
            By.CSS_SELECTOR, "input[name=courseType][data-filter='Lecture']"
        )
        semester_checkbox = self.selenium.find_element(By.CSS_SELECTOR, "input[name=semester][data-filter='ST 14']")
        search_input.send_keys("Some search text")
        program_checkbox.click()
        course_type_checkbox.click()
        semester_checkbox.click()
        reset_button.click()

        self.assertEqual(search_input.get_attribute("value"), "")
        self.assertFalse(program_checkbox.is_selected())
        self.assertFalse(course_type_checkbox.is_selected())
        self.assertFalse(semester_checkbox.is_selected())
