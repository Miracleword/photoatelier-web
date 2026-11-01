from django.contrib import admin

from .models import (
    Category,
    Client,
    Employee,
    Notification,
    Order,
    Service,
    ServiceFormat,
    StatusHistory,
)
from .order_actions import save_order
from .web_forms import StaffOrderForm


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(ServiceFormat)
class ServiceFormatAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "service_format",
        "price",
        "estimated_days",
        "is_active",
    )
    list_filter = ("category", "service_format", "is_active")
    search_fields = ("name",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "phone", "user")
    search_fields = ("full_name", "phone", "user__username")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "position", "user")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = StaffOrderForm
    list_display = (
        "order_number_display",
        "client",
        "service",
        "status",
        "total_price",
        "desired_date",
        "created_at",
    )
    list_filter = ("status", "service", "created_at")
    search_fields = (
        "client__full_name",
        "client__phone",
        "client__user__username",
    )
    readonly_fields = (
        "order_number_display",
        "total_price",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Номер заказа")
    def order_number_display(self, obj):
        return obj.order_number

    def get_search_results(self, request, queryset, search_term):
        results, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )

        number = search_term.strip().upper()
        if number.startswith("ЗК-"):
            number = number[3:]

        if number.isdigit():
            results = results | queryset.filter(pk=int(number))

        return results, may_have_duplicates

    def save_model(self, request, obj, form, change):
        save_order(obj, actor=request.user)


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "employee", "changed_at")
    list_filter = ("status",)
    readonly_fields = (
        "order",
        "status",
        "comment",
        "changed_at",
        "employee",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("client", "order", "text", "is_read", "created_at")
    readonly_fields = ("client", "order", "text", "created_at")

    def has_add_permission(self, request):
        return False

from . import user_admin  # noqa: E402,F401