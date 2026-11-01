from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from studio.models import Client, Employee
from studio.roles import (
    ADMIN,
    CLIENT,
    EMPLOYEE,
    GROUP_NAMES,
    ensure_role_groups,
    set_user_role,
)


class Command(BaseCommand):
    help = "Создаёт роли и назначает их существующим пользователям."

    def handle(self, *args, **options):
        User = get_user_model()
        plan = []

        # Сначала проверяем ВСЕ записи. При неоднозначности
        # не изменяем ничего.
        for user in User.objects.order_by("pk"):
            if user.is_superuser:
                role = ADMIN
            else:
                names = set(
                    user.groups.filter(
                        name__in=GROUP_NAMES.values()
                    ).values_list("name", flat=True)
                )

                roles = [
                    role for role, name in GROUP_NAMES.items()
                    if name in names
                ]

                if len(roles) > 1:
                    raise CommandError(
                        f"User id={user.pk}: несколько бизнес-ролей."
                    )

                if roles:
                    role = roles[0]
                else:
                    has_client = Client.objects.filter(user=user).exists()
                    has_employee = Employee.objects.filter(user=user).exists()

                    if has_client and has_employee:
                        raise CommandError(
                            f"User id={user.pk}: два профиля, "
                            "роль необходимо определить отдельно."
                        )

                    if user.is_staff:
                        role = ADMIN
                    elif has_employee:
                        role = EMPLOYEE
                    elif has_client:
                        role = CLIENT
                    else:
                        raise CommandError(
                            f"User id={user.pk}: недостаточно данных "
                            "для автоматического назначения роли."
                        )

            plan.append((user, role))

        with transaction.atomic():
            ensure_role_groups()
            for user, role in plan:
                set_user_role(user, role)

        for user, role in plan:
            self.stdout.write(f"User id={user.pk}: {role}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Роли настроены. Обработано пользователей: {len(plan)}."
            )
        )
