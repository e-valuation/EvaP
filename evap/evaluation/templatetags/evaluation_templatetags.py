from django.template import Library

register = Library()


@register.inclusion_tag("user_list_with_links.html")
def include_user_list_with_links(users):
    return dict(users=users)


@register.inclusion_tag("sortable_form_js.html")
def include_sortable_form_js():
    return dict()


@register.inclusion_tag("progress_bar.html")
def include_progress_bar(done, total, icon="", large=False):
    return dict(done=done, total=total, icon=icon, large=large)


@register.inclusion_tag("result_bar.html")
def include_result_bar(result, show_grades, questionnaire_warning=False):
    return dict(result=result, show_grades=show_grades, questionnaire_warning=questionnaire_warning)


@register.inclusion_tag("responsibility_buttons.html")
def include_responsibility_buttons(form, can_change_responsible=False):
    return dict(form=form, can_change_responsible=can_change_responsible)


@register.inclusion_tag("comment_visibility_buttons.html")
def include_comment_visibility_buttons(form):
    return dict(form=form)


@register.inclusion_tag("choice_button.html")
def include_choice_button(formelement, choice, tooltip):
    return dict(formelement=formelement, choice=choice, tooltip=tooltip)


@register.inclusion_tag("confirmation_modal.html")
def include_confirmation_modal(modal_id, title, question, action_text, btn_type):
    return dict(modal_id=modal_id, title=title, question=question, action_text=action_text, btn_type=btn_type)
