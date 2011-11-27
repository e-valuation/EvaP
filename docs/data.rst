Data Model and Data Migration
=============================

Data Model
----------

TODO

Especially to note are some constraints of this data model:
- The length of usernames is limited to 30 characters, because the default Django User model is used. As the HPI usernames are limited to 20 characters due to other systems, this is no issue for us right now. This can be changed by eiter changing the Django distribution used or by proving a custom User model.


Data Migration
--------------

The `evaluation` app is controlled by South -- a framework for Django that 
allows continuous changes in the data models without losing data.
