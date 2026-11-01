from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Client, Employee


ADMIN = "administrator"
EMPLOYEE = "employee"
CLIENT = "client"

ROLE_CHOICES = (
    (ADMIN, "Администратор"),
    (EMPLOYEE, "Сотрудник"),
    (CLIENT, "Клиент"),
)

GROUP_NAMES = {
    ADMIN: "Фотоателье: администратор",
    EMPLOYEE: "Фотоателье: сотрудник",
    CLIENT: "Фотоателье: клиент",
}


def get_role(user):
    if not user or not user.is_authenticated:
        return None

    if user.is_superuser:
        return ADMIN

    names = set(
        user.groups.filter(
            name__in=GROUP_NAMES.values()
        ).values_list("name", flat=True)
    )

    matched = [
        role for role, name in GROUP_NAMES.items()
        if name in names
    ]

    return matched[0] if len(matched) == 1 else None


def can_work(user):
    return (
        user.is_authenticated
        and user.is_active
        and get_role(user) in (ADMIN, EMPLOYEE)
    )


staff_only = user_passes_test(
    can_work,
    login_url="studio_web:login",
)


@transaction.atomic
def ensure_role_groups():
    groups = {
        role: Group.objects.get_or_create(name=name)[0]
        for role, name in GROUP_NAMES.items()
    }

    # Полный доступ администратора к моделям предметной области.
    permissions = Permission.objects.filter(
        content_type__app_label="studio"
    )

    # Управление User разрешено через защищённый UserAdmin.
    user_permissions = Permission.objects.filter(
        content_type__app_label="auth",
        content_type__model="user",
        codename__in=[
            "add_user",
            "view_user",
            "change_user",
            "delete_user",
        ],
    )

    ids = list(permissions.values_list("pk", flat=True))
    ids += list(user_permissions.values_list("pk", flat=True))
    groups[ADMIN].permissions.set(ids)

    # Сотрудник работает через отдельный интерфейс, не Django Admin.
    groups[EMPLOYEE].permissions.clear()
    groups[CLIENT].permissions.clear()

    return groups


@transaction.atomic
def set_user_role(user, role):
    if role not in GROUP_NAMES:
        raise ValidationError("Неизвестная роль пользователя.")

    if user.is_superuser and role != ADMIN:
        raise ValidationError(
            "Суперпользователю нельзя назначить другую бизнес-роль."
        )

    group, _ = Group.objects.get_or_create(
        name=GROUP_NAMES[role]
    )

    business_groups = Group.objects.filter(
        name__in=GROUP_NAMES.values()
    )
    user.groups.remove(*business_groups)
    user.groups.add(group)

    # is_staff означает вход в Django Admin, а не профессию сотрудника.
    user.is_staff = user.is_superuser or role == ADMIN
    user.save(update_fields=["is_staff"])

    full_name = user.get_full_name().strip() or user.username

    if role in (ADMIN, EMPLOYEE):
        Employee.objects.get_or_create(
            user=user,
            defaults={
                "full_name": full_name[:150],
                "position": (
                    "Администратор" if role == ADMIN else "Сотрудник"
                ),
            },
        )

    if role == CLIENT:
        Client.objects.get_or_create(
            user=user,
            defaults={
                "full_name": full_name[:150],
                "phone": "",
            },
        )

    # Старые профили при смене роли НЕ удаляем:
    # на них могут ссылаться заказы и история.
    # Роль определяется группой, а не наличием профиля.
