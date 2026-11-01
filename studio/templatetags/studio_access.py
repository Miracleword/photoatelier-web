from django import template

from studio.roles import ADMIN, can_work, get_role

register = template.Library()


@register.filter
def work_access(user):
    return can_work(user)


@register.filter
def admin_access(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and get_role(user) == ADMIN
    )
