from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.dispatch import Signal

from . import Course, Evaluation


logentry_display = Signal(providing_args=["logentry"])
"""
To display an instance of the ``LogEntry`` model to a human user,
``evap.evaluation.models.logentry_display`` will be sent out with a ``logentry`` argument.
The first received response that is not ``None`` will be used to display the log entry
to the user. The receivers are expected to return plain text.
"""


class LogEntry(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")
    datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=255)
    data = models.TextField(default="{}")

    class Meta:
        ordering = ("-datetime", "-id")

    def display(self):
        for receiver, response in logentry_display.send(self.event, logentry=self):
            if response:
                return response
        return self.action_type
