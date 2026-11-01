import json
from datetime import date
from functools import wraps

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Client, Notification, Order, Service, StatusHistory
from .order_actions import save_order
from .roles import CLIENT, get_role, set_user_role

User = get_user_model()


TOKEN_SALT = "photoatelier.client.api"
TOKEN_MAX_AGE = 7 * 24 * 60 * 60


def read_json(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def client_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return error("Необходимо войти в приложение.", 401)

        token = header.removeprefix("Bearer ").strip()

        try:
            data = signing.loads(
                token,
                salt=TOKEN_SALT,
                max_age=TOKEN_MAX_AGE,
            )
        except (
            signing.BadSignature,
            KeyError,
            TypeError,
            ValueError,
        ):
            return error("Сеанс недействителен. Войдите повторно.", 401)

        try:
            user = User.objects.get(
                pk=data["user_id"],
                is_active=True,
            )
        except (KeyError, ValueError, User.DoesNotExist):
            return error("Сеанс недействителен. Войдите повторно.", 401)

        if get_role(user) != CLIENT:
            return error("Доступ разрешён только клиентам.", 403)

        try:
            client = Client.objects.select_related("user").get(
                user=user,
            )
        except Client.DoesNotExist:
            return error("Сеанс недействителен. Войдите повторно.", 401)

        return view(request, client, *args, **kwargs)

    return wrapper


@csrf_exempt
@require_POST
def register(request):
    data = read_json(request)
    if data is None:
        return error("Передайте данные в формате JSON.")

    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))

    if not full_name or not email or not phone or not password:
        return error("Заполните все обязательные поля.")

    if len(full_name) > 150 or len(phone) > 30:
        return error("Слишком длинное имя или номер телефона.")

    try:
        validate_email(email)
        validate_password(password)
    except ValidationError as exc:
        return error(" ".join(exc.messages))

    User = get_user_model()

    if User.objects.filter(username=email).exists():
        return error("Пользователь с таким адресом уже существует.")

    with transaction.atomic():
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
        )
        client = Client.objects.create(
            user=user,
            full_name=full_name,
            phone=phone,
        )
        set_user_role(user, CLIENT)

    token = signing.dumps(
        {"user_id": user.id},
        salt=TOKEN_SALT,
    )
    return JsonResponse(
        {
            "token": token,
            "client": {
                "id": client.id,
                "full_name": client.full_name,
                "email": email,
            },
        },
        status=201,
    )


@csrf_exempt
@require_POST
def login(request):
    data = read_json(request)
    if data is None:
        return error("Передайте данные в формате JSON.")

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = authenticate(request, username=email, password=password)

    if user is None:
        return error("Неверный адрес электронной почты или пароль.", 401)

    if get_role(user) != CLIENT:
        return error("Вход доступен только клиентам фотоателье.", 403)

    try:
        client = Client.objects.get(user=user)
    except Client.DoesNotExist:
        return error("Вход доступен только клиентам фотоателье.", 403)

    token = signing.dumps(
        {"user_id": user.id},
        salt=TOKEN_SALT,
    )
    return JsonResponse(
        {
            "token": token,
            "client": {
                "id": client.id,
                "full_name": client.full_name,
                "email": user.email,
            },
        }
    )


@require_GET
def services(request):
    items = Service.objects.filter(is_active=True).select_related(
        "category"
    ).order_by("category__name", "name")

    return JsonResponse(
        {
            "services": [
                {
                    "id": item.id,
                    "name": item.name,
                    "category": item.category.name,
                    "description": item.description,
                    "price": str(item.price),
                    "estimated_days": item.estimated_days,
                }
                for item in items
            ]
        }
    )


@require_GET
@client_required
def my_orders(request, client):
    items = (
        Order.objects.filter(client=client)
        .select_related("service")
        .order_by("-created_at")
    )

    return JsonResponse(
        {
            "orders": [
                {
                    "id": item.id,
                    "number": item.order_number,
                    "service": item.service.name,
                    "quantity": item.quantity,
                    "total_price": str(item.total_price),
                    "desired_date": item.desired_date.isoformat(),
                    "status": item.status,
                    "status_name": item.get_status_display(),
                    "comment": item.comment,
                    "employee_comment": item.employee_comment,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ]
        }
    )


@csrf_exempt
@require_POST
@client_required
def create_order(request, client):
    data = read_json(request)
    if data is None:
        return error("Передайте данные в формате JSON.")

    raw_service_id = data.get("service_id")
    raw_quantity = data.get("quantity", 1)

    if (
        isinstance(raw_service_id, bool)
        or not isinstance(raw_service_id, int)
        or raw_service_id <= 0
    ):
        return error("Укажите корректную услугу.")

    if (
        isinstance(raw_quantity, bool)
        or not isinstance(raw_quantity, int)
    ):
        return error("Количество должно быть целым числом.")

    try:
        desired_date = date.fromisoformat(
            str(data.get("desired_date", ""))
        )
    except (TypeError, ValueError):
        return error("Укажите корректную дату.")

    comment = data.get("comment", "")
    if not isinstance(comment, str):
        return error("Комментарий должен быть текстом.")

    try:
        service = Service.objects.get(
            pk=raw_service_id,
            is_active=True,
        )
    except Service.DoesNotExist:
        return error("Услуга не найдена или недоступна.", 404)

    order = Order(
        client=client,
        service=service,
        desired_date=desired_date,
        quantity=raw_quantity,
        comment=comment.strip(),
    )

    try:
        order = save_order(order, actor=client.user)
    except ValidationError as exc:
        return error(" ".join(exc.messages))

    return JsonResponse(
        {
            "id": order.id,
            "number": order.order_number,
            "status": order.status,
            "status_name": order.get_status_display(),
            "total_price": str(order.total_price),
        },
        status=201,
    )


@require_GET
@client_required
def notifications(request, client):
    items = Notification.objects.filter(client=client)[:50]

    return JsonResponse(
        {
            "notifications": [
                {
                    "id": item.id,
                    "order_id": item.order_id,
                    "text": item.text,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ]
        }
    )