from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .api import client_required, error, read_json
from .models import Order, Service
from .order_actions import save_order


SORT_FIELDS = {
    "-created_at",
    "created_at",
    "total_price",
    "-total_price",
    "desired_date",
    "-desired_date",
}

EDITABLE_FIELDS = {
    "service_id",
    "quantity",
    "desired_date",
    "comment",
}


def serialize_order(order):
    return {
        "id": order.pk,
        "number": order.order_number,
        "service_id": order.service_id,
        "service": order.service.name,
        "quantity": order.quantity,
        "total_price": str(order.total_price),
        "desired_date": order.desired_date.isoformat(),
        "status": order.status,
        "status_name": order.get_status_display(),
        "comment": order.comment,
        "employee_comment": order.employee_comment,
        "created_at": order.created_at.isoformat(),
        "can_edit": order.status == Order.Status.NEW,
        "can_delete": order.status == Order.Status.NEW,
    }


def own_order(client, pk):
    return (
        Order.objects.filter(client=client, pk=pk)
        .select_related("service")
        .first()
    )


@require_GET
@client_required
def order_list(request, client):
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "-created_at")

    if status and status not in dict(Order.Status.choices):
        return error("Неизвестный статус.")

    if sort not in SORT_FIELDS:
        return error("Недопустимый способ сортировки.")

    orders = Order.objects.filter(
        client=client
    ).select_related("service")

    if status:
        orders = orders.filter(status=status)

    orders = orders.order_by(sort, "-pk")

    return JsonResponse(
        {
            "orders": [serialize_order(order) for order in orders],
        },
        json_dumps_params={"ensure_ascii": False},
    )


@require_GET
@client_required
def order_detail(request, client, pk):
    order = own_order(client, pk)
    if order is None:
        return error("Заказ не найден.", 404)

    return JsonResponse(
        {"order": serialize_order(order)},
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_POST
@client_required
def order_update(request, client, pk):
    data = read_json(request)
    if data is None:
        return error("Передайте данные в формате JSON.")

    if not data:
        return error("Не указаны данные для изменения.")

    if set(data) - EDITABLE_FIELDS:
        return error(
            "Разрешено менять только услугу, количество, "
            "дату и комментарий."
        )

    with transaction.atomic():
        order = own_order(client, pk)
        if order is None:
            return error("Заказ не найден.", 404)

        if order.status != Order.Status.NEW:
            return error(
                "Изменить можно только новый заказ.",
                403,
            )

        if "service_id" in data:
            service_id = data["service_id"]
            if (
                isinstance(service_id, bool)
                or not isinstance(service_id, int)
                or service_id <= 0
            ):
                return error("Укажите корректную услугу.")

            if service_id != order.service_id:
                service = Service.objects.filter(
                    pk=service_id,
                    is_active=True,
                ).first()

                if service is None:
                    return error(
                        "Услуга не найдена или недоступна.",
                        404,
                    )
                order.service = service

        if "quantity" in data:
            quantity = data["quantity"]
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
            ):
                return error("Количество должно быть целым числом.")
            order.quantity = quantity

        if "desired_date" in data:
            value = data["desired_date"]
            if not isinstance(value, str):
                return error("Укажите корректную дату.")
            try:
                order.desired_date = date.fromisoformat(value)
            except ValueError:
                return error("Укажите корректную дату.")

        if "comment" in data:
            if not isinstance(data["comment"], str):
                return error("Комментарий должен быть текстом.")
            order.comment = data["comment"].strip()

        try:
            order = save_order(order, actor=client.user)
        except ValidationError as exc:
            return error(" ".join(exc.messages))
        except PermissionDenied:
            return error("Недостаточно прав.", 403)

    return JsonResponse(
        {"order": serialize_order(order)},
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_POST
@client_required
def order_delete(request, client, pk):
    with transaction.atomic():
        order = own_order(client, pk)

        if order is None:
            return error("Заказ не найден.", 404)

        if order.status != Order.Status.NEW:
            return error(
                "Удалить можно только новый заказ.",
                403,
            )

        number = order.order_number
        order.delete()

    return JsonResponse(
        {
            "deleted": True,
            "number": number,
        },
        json_dumps_params={"ensure_ascii": False},
    )
