from django.template import Library

register = Library()


@register.filter
def has_active_links(links):
    return any(link.is_active for link in links)


@register.filter
def has_inactive_links(links):
    return any(not link.is_active for link in links)
