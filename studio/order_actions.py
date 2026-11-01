from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Employee, Notification, Order, StatusHistory
from .roles import CLIENT, can_work, get_role


@transaction.atomic
def save_order(order, *, actor):
    """
    Сохраняет заказ и сопутствующие события.
    actor — реальный автор текущего действия.
    Ответственный за заказ и автор изменения — разные понятия.
    """
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("Необходимо войти в приложение.")

    previous = None
    if order.pk:
        previous = Order.objects.get(pk=order.pk)

    is_worker = can_work(actor)
    is_client = get_role(actor) == CLIENT

    if not is_worker and not is_client:
        raise PermissionDenied("Недостаточно прав.")

    if is_client:
        profile = getattr(actor, "client_profile", None)
        if profile is None or order.client_id != profile.pk:
            raise PermissionDenied("Недоступный заказ.")

        if previous is not None:
            if previous.client_id != profile.pk:
                raise PermissionDenied("Недоступный заказ.")
            if previous.status != Order.Status.NEW:
                raise ValidationError(
                    "Клиент может изменять только новый заказ."
                )
            if (
                order.status != previous.status
                or order.employee_id != previous.employee_id
                or order.employee_comment != previous.employee_comment
            ):
                raise PermissionDenied(
                    "Клиент не может изменять служебные поля заказа."
                )
        elif (
            order.status != Order.Status.NEW
            or order.employee_id is not None
            or order.employee_comment
        ):
            raise PermissionDenied(
                "При создании клиентского заказа служебные поля запрещены."
            )

    if (
        previous is not None
        and previous.client_id != order.client_id
    ):
        raise ValidationError(
            "Нельзя менять клиента существующего заказа. "
            "При необходимости создайте новый заказ."
        )

    if not isinstance(order.quantity, int) or isinstance(order.quantity, bool):
        raise ValidationError(
            {"quantity": "Количество должно быть целым числом."}
        )

    if not 1 <= order.quantity <= 100:
        raise ValidationError(
            {"quantity": "Количество должно быть от 1 до 100."}
        )

    if order.desired_date is None:
        raise ValidationError(
            {"desired_date": "Укажите желаемую дату."}
        )

    date_changed = (
        previous is None
        or previous.desired_date != order.desired_date
    )
    if date_changed and order.desired_date < timezone.localdate():
        raise ValidationError(
            {"desired_date": "Новая дата не может быть в прошлом."}
        )

    for field in ("comment", "employee_comment"):
        value = getattr(order, field)
        if not isinstance(value, str):
            raise ValidationError(
                {field: "Комментарий должен быть текстом."}
            )
        if len(value) > 2000:
            raise ValidationError(
                {field: "Допускается не более 2000 символов."}
            )

    if (
        order.status == Order.Status.CANCELLED
        and not order.employee_comment.strip()
    ):
        raise ValidationError(
            {"employee_comment": "Укажите причину отмены."}
        )

    service_changed = (
        previous is None
        or previous.service_id != order.service_id
    )
    if service_changed and not order.service.is_active:
        raise ValidationError(
            {"service": "Выбранная услуга недоступна."}
        )

    if order.service.price < 0:
        raise ValidationError(
            {"service": "У выбранной услуги отрицательная цена."}
        )

    recalculate = (
        previous is None
        or service_changed
        or previous.quantity != order.quantity
    )

    if recalculate:
        order.total_price = order.service.price * order.quantity
    else:
        # При изменении статуса/комментария сохраняем прежнюю стоимость.
        # Произвольная подмена total_price не принимается.
        order.total_price = previous.total_price

    employee = None
    if is_worker:
        employee = Employee.objects.filter(user=actor).first()
        if employee is None:
            raise ValidationError(
                "У пользователя отсутствует профиль сотрудника. "
                "Проверьте назначение роли в панели администратора."
            )

        # Первый сотрудник, обработавший нераспределённый заказ,
        # становится ответственным.
        # При следующих правках ответственный не перезаписывается.
        if order.employee_id is None:
            order.employee = employee

    order.full_clean()
    order.save()

    status_changed = (
        previous is None
        or previous.status != order.status
    )

    if status_changed:
        StatusHistory.objects.create(
            order=order,
            status=order.status,
            comment=order.employee_comment,
            employee=employee,
        )
        Notification.objects.create(
            client=order.client,
            order=order,
            text=(
                f"Заказ {order.order_number}: "
                f"{order.get_status_display().lower()}."
            ),
        )

    return order
