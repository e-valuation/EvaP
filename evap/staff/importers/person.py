from typing import Iterable

from django.utils.html import format_html
from django.utils.translation import gettext as _

from evap.evaluation.models import Contribution, Evaluation, UserProfile
from evap.staff.tools import ImportType, create_user_list_html_string_for_message

from .base import ImporterLog
from .user import import_users


def add_participants_to(
    evaluation: Evaluation, users: Iterable[UserProfile], test_run: bool, importer_log: ImporterLog
):
    evaluation_participants = evaluation.participants.all()
    already_related = [user for user in users if user in evaluation_participants]
    users_to_add = [user for user in users if user not in evaluation_participants]

    if already_related:
        msg = format_html(
            _("The following {} users are already participants in evaluation {}:"),
            len(already_related),
            evaluation.full_name,
        )
        msg += create_user_list_html_string_for_message(already_related)
        importer_log.add_warning(msg)

    if not test_run:
        evaluation.participants.add(*users_to_add)
        msg = format_html(_("{} participants added to the evaluation {}:"), len(users_to_add), evaluation.full_name)
    else:
        msg = format_html(
            _("{} participants would be added to the evaluation {}:"), len(users_to_add), evaluation.full_name
        )
    msg += create_user_list_html_string_for_message(users_to_add)

    importer_log.add_success(msg)


def add_contributors_to(
    evaluation: Evaluation, users: Iterable[UserProfile], test_run: bool, importer_log: ImporterLog
):
    already_related_contributions = Contribution.objects.filter(evaluation=evaluation, contributor__in=users)
    already_related = {contribution.contributor for contribution in already_related_contributions}
    if already_related:
        msg = format_html(
            _("The following {} users are already contributing to evaluation {}:"),
            len(already_related),
            evaluation.full_name,
        )
        msg += create_user_list_html_string_for_message(already_related)
        importer_log.add_warning(msg)

    users_to_add = [user for user in users if not user.pk or user not in already_related]

    if not test_run:
        for user in users_to_add:
            order = Contribution.objects.filter(evaluation=evaluation).count()
            Contribution.objects.create(evaluation=evaluation, contributor=user, order=order)
        msg = format_html(_("{} contributors added to the evaluation {}:"), len(users_to_add), evaluation.full_name)
    else:
        msg = format_html(
            _("{} contributors would be added to the evaluation {}:"), len(users_to_add), evaluation.full_name
        )
    msg += create_user_list_html_string_for_message(users_to_add)
    importer_log.add_success(msg)


def import_persons_from_file(
    import_type: ImportType, evaluation: Evaluation, test_run: bool, file_content
) -> ImporterLog:
    # the user import also makes these users active
    users, importer_log = import_users(file_content, test_run)

    if import_type == ImportType.PARTICIPANT:
        add_participants_to(evaluation, users, test_run, importer_log)
    else:
        assert import_type == ImportType.CONTRIBUTOR
        add_contributors_to(evaluation, users, test_run, importer_log)

    return importer_log


def import_persons_from_evaluation(
    import_type: ImportType, evaluation: Evaluation, test_run: bool, source_evaluation: Evaluation
) -> ImporterLog:
    importer_log = ImporterLog()

    if import_type == ImportType.PARTICIPANT:
        users = source_evaluation.participants.all()
        add_participants_to(evaluation, users, test_run, importer_log)
    else:
        assert import_type == ImportType.CONTRIBUTOR
        users = UserProfile.objects.filter(contributions__evaluation=source_evaluation)
        add_contributors_to(evaluation, users, test_run, importer_log)

    if not test_run:
        UserProfile.objects.filter(pk__in=users).update(is_active=True)

    return importer_log
