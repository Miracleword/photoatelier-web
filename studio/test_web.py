from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Client, Notification, Order, Service
from .models import StatusHistory
from .roles import (
    ADMIN,
    CLIENT,
    EMPLOYEE,
    ensure_role_groups,
    set_user_role,
)


class StaffWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            username="web_staff",
            password="Test-password-123",
            is_staff=True,
        )
        user = User.objects.create_user(
            username="web_client",
            password="Test-password-123",
        )
        cls.customer = Client.objects.create(
            user=user,
            full_name="Тестовый клиент",
            phone="0000000000",
        )
        category = Category.objects.create(name="Тестовая категория")
        cls.service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            price=Decimal("100.00"),
        )

        ensure_role_groups()
        set_user_role(cls.staff, EMPLOYEE)
        set_user_role(user, CLIENT)

    def setUp(self):
        self.client.force_login(self.staff)
        self.order = Order.objects.create(
            client=self.customer,
            service=self.service,
            desired_date=timezone.localdate() + timedelta(days=1),
            quantity=1,
            total_price=Decimal("100.00"),
        )

    def payload(self, **changes):
        result = {
            "client": self.customer.pk,
            "service": self.service.pk,
            "desired_date": self.order.desired_date.isoformat(),
            "quantity": 2,
            "status": Order.Status.NEW,
            "comment": "",
            "employee_comment": "",
        }
        result.update(changes)
        return result

    def test_anonymous_redirect(self):
        self.client.logout()
        response = self.client.get(reverse("studio_web:order_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_regular_client_cannot_open_staff_pages(self):
        self.client.force_login(self.customer.user)
        response = self.client.get(reverse("studio_web:order_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_and_detail(self):
        for name, kwargs in [
            ("order_list", {}),
            ("order_detail", {"pk": self.order.pk}),
        ]:
            response = self.client.get(
                reverse(f"studio_web:{name}", kwargs=kwargs)
            )
            self.assertEqual(response.status_code, 200)

    def test_create(self):
        response = self.client.post(
            reverse("studio_web:order_create"),
            self.payload(),
        )
        self.assertEqual(response.status_code, 302)
        created = Order.objects.latest("pk")
        self.assertEqual(created.total_price, Decimal("200.00"))
        self.assertTrue(
            StatusHistory.objects.filter(order=created).exists()
        )
        self.assertTrue(
            Notification.objects.filter(order=created).exists()
        )

    def test_update_status(self):
        response = self.client.post(
            reverse("studio_web:order_edit", args=[self.order.pk]),
            self.payload(
                quantity=1,
                status=Order.Status.ACCEPTED,
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ACCEPTED)
        self.assertEqual(
            self.order.total_price,
            Decimal("100.00"),
        )
        self.assertTrue(
            Notification.objects.filter(order=self.order).exists()
        )

    def test_invalid_quantity(self):
        response = self.client.post(
            reverse("studio_web:order_create"),
            self.payload(quantity=0),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_delete_requires_post(self):
        url = reverse("studio_web:order_delete", args=[self.order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())

    def test_cannot_delete_ready_order(self):
        self.order.status = Order.Status.READY
        self.order.save()
        self.client.post(
            reverse("studio_web:order_delete", args=[self.order.pk])
        )
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_filter(self):
        response = self.client.get(
            reverse("studio_web:order_list"),
            {"status": Order.Status.READY},
        )
        self.assertEqual(list(response.context["orders"]), [])

    def test_sort(self):
        second = Order.objects.create(
            client=self.customer,
            service=self.service,
            desired_date=self.order.desired_date,
            quantity=3,
            total_price=Decimal("300.00"),
        )
        response = self.client.get(
            reverse("studio_web:order_list"),
            {"sort": "-total_price"},
        )
        self.assertEqual(
            list(response.context["orders"]),
            [second, self.order],
        )

    def test_employee_cannot_open_admin(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_administrator_can_open_admin(self):
        set_user_role(self.staff, ADMIN)
        self.client.force_login(self.staff)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

    def test_employee_profile_created(self):
        self.assertTrue(
            self.staff.employee_profile.pk
        )

    def test_only_one_business_role_after_switch(self):
        from .roles import GROUP_NAMES, get_role

        set_user_role(self.staff, ADMIN)
        set_user_role(self.staff, EMPLOYEE)

        self.assertEqual(get_role(self.staff), EMPLOYEE)
        self.assertEqual(
            self.staff.groups.filter(
                name__in=GROUP_NAMES.values()
            ).count(),
            1,
        )

    def test_administrator_cannot_change_superuser(self):
        User = get_user_model()
        root = User.objects.create_superuser(
            username="protected_root",
            email="root@example.test",
            password="Test-password-123",
        )
        set_user_role(self.staff, ADMIN)
        self.client.force_login(self.staff)

        url = reverse("admin:auth_user_change", args=[root.pk])
        response = self.client.post(
            url,
            {
                "username": root.username,
                "role": CLIENT,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 403)
        root.refresh_from_db()
        self.assertTrue(root.is_superuser)

    def test_administrator_creates_employee(self):
        from .roles import get_role

        set_user_role(self.staff, ADMIN)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "created_employee",
                "email": "employee@example.test",
                "first_name": "Тест",
                "last_name": "Сотрудник",
                "password1": "Strong-course-password-827!",
                "password2": "Strong-course-password-827!",
                "role": EMPLOYEE,
                "_save": "Сохранить",
            },
        )

        self.assertEqual(response.status_code, 302)

        created = get_user_model().objects.get(
            username="created_employee"
        )
        self.assertEqual(get_role(created), EMPLOYEE)
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertTrue(
            hasattr(created, "employee_profile")
        )
