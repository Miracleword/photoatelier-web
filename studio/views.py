from datetime import date

from django.db.models import Count, Sum
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import Order
from .roles import staff_only


@staff_only
@require_GET
def report(request):
    start_text = request.GET.get("start", "").strip()
    end_text = request.GET.get("end", "").strip()
    selected_status = request.GET.get("status", "")
    error = ""

    if selected_status not in dict(Order.Status.choices):
        selected_status = ""

    try:
        start = date.fromisoformat(start_text) if start_text else None
        end = date.fromisoformat(end_text) if end_text else None
        if start and end and start > end:
            error = "Начальная дата не может быть позже конечной."
    except ValueError:
        start = end = None
        error = "Проверьте даты."

    orders = Order.objects.select_related("client", "service")

    if error:
        orders = orders.none()
    else:
        if start:
            orders = orders.filter(created_at__date__gte=start)
        if end:
            orders = orders.filter(created_at__date__lte=end)
        if selected_status:
            orders = orders.filter(status=selected_status)

    counts = {
        item["status"]: item["count"]
        for item in orders.values("status").annotate(count=Count("pk"))
    }

    status_rows = [
        (label, counts.get(value, 0))
        for value, label in Order.Status.choices
    ]

    completed_value = orders.filter(
        status__in=[Order.Status.READY, Order.Status.ISSUED]
    ).aggregate(total=Sum("total_price"))["total"] or 0

    return render(
        request,
        "studio/report.html",
        {
            "orders": orders.order_by("-created_at", "-pk"),
            "total": sum(counts.values()),
            "status_rows": status_rows,
            "completed_value": completed_value,
            "start_text": start_text,
            "end_text": end_text,
            "selected_status": selected_status,
            "statuses": Order.Status.choices,
            "error": error,
        },
    )
