from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.utils import timezone

from .models import Order, Service
from .roles import can_work


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин")
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput,
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not can_work(user):
            raise forms.ValidationError(
                "Вход разрешён только сотрудникам.",
                code="not_staff",
            )


class StaffOrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            "client",
            "service",
            "desired_date",
            "quantity",
            "status",
            "comment",
            "employee_comment",
        ]
        widgets = {
            "desired_date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "quantity": forms.NumberInput(
                attrs={"min": 1, "max": 100}
            ),
            "comment": forms.Textarea(
                attrs={"rows": 3, "maxlength": 2000}
            ),
            "employee_comment": forms.Textarea(
                attrs={"rows": 3, "maxlength": 2000}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        condition = Q(is_active=True)
        if self.instance.pk:
            condition |= Q(pk=self.instance.service_id)

        self.fields["service"].queryset = (
            Service.objects.filter(condition)
            .select_related("service_format")
            .order_by("name")
        )
        self.fields["client"].queryset = (
            self.fields["client"].queryset.order_by("full_name")
        )
        if self.instance.pk:
            self.fields["client"].disabled = True
        self.fields["desired_date"].input_formats = ["%Y-%m-%d"]
        self.fields["status"].initial = Order.Status.NEW

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if not 1 <= quantity <= 100:
            raise forms.ValidationError(
                "Количество должно быть от 1 до 100."
            )
        return quantity

    def clean_desired_date(self):
        value = self.cleaned_data["desired_date"]
        unchanged = (
            self.instance.pk
            and value == self.instance.desired_date
        )
        if value < timezone.localdate() and not unchanged:
            raise forms.ValidationError(
                "Нельзя назначить новую дату в прошлом."
            )
        return value

    def clean(self):
        cleaned = super().clean()

        for field in ("comment", "employee_comment"):
            if len(cleaned.get(field, "")) > 2000:
                self.add_error(
                    field,
                    "Допускается не более 2000 символов.",
                )

        if (
            cleaned.get("status") == Order.Status.CANCELLED
            and not cleaned.get("employee_comment")
        ):
            self.add_error(
                "employee_comment",
                "Укажите причину отмены.",
            )

        service = cleaned.get("service")
        quantity = cleaned.get("quantity")

        if service and service.price < 0:
            self.add_error(
                "service",
                "У выбранной услуги отрицательная цена. "
                "Исправьте её в справочнике.",
            )

        if (
            service
            and quantity
            and service.price * quantity > 99999999.99
        ):
            self.add_error(
                "quantity",
                "Стоимость превышает допустимое значение.",
            )

        return cleaned
