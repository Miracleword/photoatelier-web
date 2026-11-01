from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.http import require_http_methods

from .models import Employee, Notification, Order, StatusHistory
from .order_actions import save_order
from .roles import staff_only
from .web_forms import StaffLoginForm, StaffOrderForm

SORT_OPTIONS = {
    "-created_at": "Сначала новые",
    "created_at": "Сначала старые",
    "desired_date": "По желаемой дате",
    "total_price": "По стоимости: возрастание",
    "-total_price": "По стоимости: убывание",
}

DELETABLE_STATUSES = (
    Order.Status.NEW,
    Order.Status.CANCELLED,
)


class StaffLoginView(LoginView):
    template_name = "studio/web/login.html"
    authentication_form = StaffLoginForm

    def get_success_url(self):
        return (
            self.get_redirect_url()
            or str(reverse_lazy("studio_web:order_list"))
        )


@require_POST
def staff_logout(request):
    logout(request)
    return redirect("studio_web:login")


@staff_only
@require_GET
def order_list(request):
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "-created_at")
    query = request.GET.get("q", "").strip()

    if sort not in SORT_OPTIONS:
        sort = "-created_at"

    valid_statuses = dict(Order.Status.choices)
    if status not in valid_statuses:
        status = ""

    orders = Order.objects.select_related(
        "client",
        "service",
        "service__service_format",
    )

    if status:
        orders = orders.filter(status=status)

    if query:
        condition = (
            Q(client__full_name__icontains=query)
            | Q(client__phone__icontains=query)
            | Q(service__name__icontains=query)
        )
        number = query.upper().removeprefix("ЗК-")
        if number.isascii() and number.isdigit() and len(number) <= 18:
            condition |= Q(pk=int(number))

        orders = orders.filter(condition)

    orders = orders.order_by(sort, "-pk")

    return render(
        request,
        "studio/web/order_list.html",
        {
            "orders": orders,
            "selected_status": status,
            "selected_sort": sort,
            "query": query,
            "statuses": Order.Status.choices,
            "sort_options": SORT_OPTIONS.items(),
        },
    )


@staff_only
@require_GET
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related(
            "client",
            "service",
            "service__service_format",
            "employee",
        ),
        pk=pk,
    )

    return render(
        request,
        "studio/web/order_detail.html",
        {
            "order": order,
            "history": order.status_history.select_related("employee"),
            "can_delete": order.status in DELETABLE_STATUSES,
        },
    )


@staff_only
@require_http_methods(["GET", "POST"])
def order_edit(request, pk=None):
    order = get_object_or_404(Order, pk=pk) if pk else None

    form = StaffOrderForm(
        request.POST if request.method == "POST" else None,
        instance=order,
    )

    if request.method == "POST" and form.is_valid():
        try:
            saved = save_order(
                form.save(commit=False),
                actor=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, "Заказ сохранён.")
            return redirect(
                "studio_web:order_detail",
                pk=saved.pk,
            )

    return render(
        request,
        "studio/web/order_form.html",
        {
            "form": form,
            "editing": order is not None,
            "order": order,
        },
    )


@staff_only
@require_http_methods(["GET", "POST"])
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if order.status not in DELETABLE_STATUSES:
        messages.error(
            request,
            "Удалить можно только новый или отменённый заказ.",
        )
        return redirect("studio_web:order_detail", pk=pk)

    if request.method == "POST":
        number = order.order_number
        with transaction.atomic():
            order.delete()

        messages.success(request, f"Заказ {number} удалён.")
        return redirect("studio_web:order_list")

    return render(
        request,
        "studio/web/order_delete.html",
        {"order": order},
    )
