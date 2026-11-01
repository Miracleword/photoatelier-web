from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Client, Order, Service, ServiceFormat
from .roles import ADMIN, CLIENT, EMPLOYEE, ensure_role_groups, set_user_role


class CatalogInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        ensure_role_groups()

        cls.worker = User.objects.create_user(
            username="catalog_worker",
            password="Strong-test-password-654!",
        )
        set_user_role(cls.worker, EMPLOYEE)

        cls.customer_user = User.objects.create_user(
            username="catalog_customer",
            password="Strong-test-password-654!",
        )
        set_user_role(cls.customer_user, CLIENT)
        cls.customer = Client.objects.get(user=cls.customer_user)

        cls.category = Category.objects.create(name="Категория теста")
        cls.format = ServiceFormat.objects.create(name="Формат теста")
        cls.service = Service.objects.create(
            category=cls.category,
            service_format=cls.format,
            name="Услуга теста",
            price=Decimal("100.00"),
        )
        cls.order = Order.objects.create(
            client=cls.customer,
            service=cls.service,
            desired_date=timezone.localdate() + timedelta(days=1),
            quantity=1,
            total_price=Decimal("100.00"),
        )

    def setUp(self):
        self.client.force_login(self.worker)

    def test_employee_menu_and_no_admin_link(self):
        response = self.client.get(reverse("studio_web:order_list"))
        self.assertContains(response, "Категории")
        self.assertContains(response, "Форматы")
        self.assertContains(response, "Клиенты")
        self.assertNotContains(response, "Панель администратора")
        self.assertNotContains(
            response,
            reverse("studio_web:order_edit", args=[self.order.pk]),
        )
        self.assertEqual(
            response.content.decode().count(
                reverse("studio_web:order_create")
            ),
            1,
        )

    def test_admin_menu(self):
        set_user_role(self.worker, ADMIN)
        self.client.force_login(self.worker)
        response = self.client.get(reverse("studio_web:order_list"))
        self.assertContains(response, "Панель администратора")

    def test_catalog_pages(self):
        for kind, obj in [
            ("services", self.service),
            ("categories", self.category),
            ("formats", self.format),
        ]:
            urls = [
                reverse("studio_catalog:list", args=[kind]),
                reverse("studio_catalog:detail", args=[kind, obj.pk]),
                reverse("studio_catalog:create", args=[kind]),
                reverse("studio_catalog:edit", args=[kind, obj.pk]),
                reverse("studio_catalog:delete", args=[kind, obj.pk]),
            ]
            for url in urls:
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_create_and_edit_service(self):
        payload = {
            "category": self.category.pk,
            "service_format": self.format.pk,
            "name": "Дополнительная услуга",
            "description": "Описание",
            "price": "250.00",
            "estimated_days": 2,
            "is_active": "on",
        }
        response = self.client.post(
            reverse("studio_catalog:create", args=["services"]),
            payload,
        )
        self.assertEqual(response.status_code, 302)

        obj = Service.objects.get(name="Дополнительная услуга")
        payload["price"] = "300.00"
        response = self.client.post(
            reverse("studio_catalog:edit", args=["services", obj.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.price, Decimal("300.00"))

    def test_delete_unused_category_requires_post(self):
        obj = Category.objects.create(name="Удаляемая категория")
        url = reverse(
            "studio_catalog:delete",
            args=["categories", obj.pk],
        )
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Category.objects.filter(pk=obj.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Category.objects.filter(pk=obj.pk).exists())

    def test_used_service_is_protected(self):
        response = self.client.post(
            reverse(
                "studio_catalog:delete",
                args=["services", self.service.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Service.objects.filter(pk=self.service.pk).exists()
        )

    def test_client_cannot_modify_catalog(self):
        self.client.force_login(self.customer_user)
        response = self.client.post(
            reverse("studio_catalog:create", args=["categories"]),
            {"name": "Запрещённая категория", "description": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Category.objects.filter(name="Запрещённая категория").exists()
        )

    def test_clients_pages(self):
        self.assertEqual(
            self.client.get(
                reverse("studio_catalog:clients")
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "studio_catalog:client_detail",
                    args=[self.customer.pk],
                )
            ).status_code,
            200,
        )

    def test_report_uses_application_template(self):
        response = self.client.get("/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "studio/web/base.html")
        self.assertContains(
            response,
            reverse("studio_web:order_detail", args=[self.order.pk]),
        )

    def test_report_invalid_period(self):
        response = self.client.get(
            "/reports/",
            {"start": "2026-12-31", "end": "2026-01-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Начальная дата не может быть позже конечной.",
        )

    def test_catalog_sort_and_filter(self):
        hidden = Service.objects.create(
            category=self.category,
            name="Отключённая услуга",
            price=Decimal("500.00"),
            is_active=False,
        )
        response = self.client.get(
            reverse("studio_catalog:list", args=["services"]),
            {"active": "no", "sort": "-price"},
        )
        self.assertEqual(
            list(response.context["items"]),
            [hidden],
        )

    def test_client_cannot_open_report(self):
        self.client.force_login(self.customer_user)
        response = self.client.get("/reports/")
        self.assertEqual(response.status_code, 302)
