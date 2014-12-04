Source Code
===========

EvaP is a standard Django project, divided up into several applications:

:py:mod:`evaluation`
    contains all the data models relevant for the evaluation, but no views.
    It also contains some generic code used by other applications.

:py:mod:`staff`
    provides views for the student representatives

:py:mod:`lecturer`
    provides views for lecturers

:py:mod:`results`
    provides views to show results and produce exports

:py:mod:`student`
    provides views relevant for students (voting etc.)

Data Import
-----------

The key module for data imports is :py:mod:`staff.importers`.
