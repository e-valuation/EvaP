from django.utils.translation import ugettext_lazy as _

FEEDBACK_OPEN = 0
FEEDBACK_CLOSED = 1
FEEDBACK_STATES = (
    (FEEDBACK_OPEN, _('Unprocessed Feedback')),
    (FEEDBACK_CLOSED, _('Processed Feedback')),
)