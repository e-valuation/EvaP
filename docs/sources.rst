Source Code
===========

EvaP is a standard Django project, divided up into several applications:

- *evaluation* contains all the data models relevant for the evaluation, but 
  no views. It also contains some generic code used by other applications.
- *fsr* provides views for the student representatives
- *lecturer* provides views for lecturers
- *results* provides views to show results and produce exports
- *student* provides views relevant for students (voting etc.)
