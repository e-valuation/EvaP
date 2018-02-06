from django.conf import settings


def legal_notice_active(request):
    return {'LEGAL_NOTICE_ACTIVE': settings.LEGAL_NOTICE_ACTIVE}
