from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .roles import (
    ADMIN,
    CLIENT,
    EMPLOYEE,
    ROLE_CHOICES,
    get_role,
    set_user_role,
)


User = get_user_model()


class RoleUserChangeForm(UserChangeForm):
    role = forms.ChoiceField(
        label="Роль",
        choices=ROLE_CHOICES,
    )

    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = get_role(self.instance) or CLIENT

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.instance.is_superuser and role != ADMIN:
            raise forms.ValidationError(
                "Суперпользователю доступна только роль администратора."
            )
        return role


class RoleUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Роль",
        choices=ROLE_CHOICES,
        initial=CLIENT,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Пользователь с таким email уже существует."
            )

        return email


class PhotoAtelierUserAdmin(UserAdmin):
    form = RoleUserChangeForm
    add_form = RoleUserCreationForm
    actions = None

    list_display = (
        "username",
        "email",
        "role_display",
        "is_active",
        "is_superuser",
    )
    list_filter = ("is_active", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)

    @admin.display(description="Роль")
    def role_display(self, obj):
        return dict(ROLE_CHOICES).get(
            get_role(obj),
            "Не назначена / конфликт",
        )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    "Новая учётная запись",
                    {
                        "fields": (
                            "username",
                            "email",
                            "first_name",
                            "last_name",
                            "password1",
                            "password2",
                            "role",
                        )
                    },
                ),
            )

        sections = [
            (
                "Учётная запись",
                {"fields": ("username", "password")},
            ),
            (
                "Контактные данные",
                {"fields": ("first_name", "last_name", "email")},
            ),
            (
                "Доступ",
                {"fields": ("role", "is_active")},
            ),
        ]

        if request.user.is_superuser:
            sections.append(
                (
                    "Системные права",
                    {"fields": ("is_superuser",)},
                )
            )

        return tuple(sections)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.pk == request.user.pk:
            # Защита от случайного отключения/понижения самого себя.
            return ("role", "is_active", "is_superuser")
        return ()

    def has_view_permission(self, request, obj=None):
        if (
            obj is not None
            and obj.is_superuser
            and not request.user.is_superuser
        ):
            return False
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if (
            obj is not None
            and obj.is_superuser
            and not request.user.is_superuser
        ):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            if obj.pk == request.user.pk:
                return False
            if obj.is_superuser and not request.user.is_superuser:
                return False
        return super().has_delete_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        role = form.cleaned_data.get("role")

        if role is None:
            # Роль может быть readonly для собственной записи.
            role = get_role(form.instance)

        if role:
            set_user_role(form.instance, role)


if admin.site.is_registered(User):
    admin.site.unregister(User)

admin.site.register(User, PhotoAtelierUserAdmin)
