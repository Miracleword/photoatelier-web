from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.utils import timezone

from .api import TOKEN_SALT
from .models import Category, Client, Order, Service
from .order_actions import save_order
from .roles import (
    CLIENT,
    EMPLOYEE,
    ensure_role_groups,
    set_user_role,
)


class ClientOrderApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        ensure_role_groups()

        cls.buyer = User.objects.create_user(
            username="crud_buyer"
        )
        set_user_role(cls.buyer, CLIENT)
        cls.customer = Client.objects.get(user=cls.buyer)

        cls.other_buyer = User.objects.create_user(
            username="crud_other_buyer"
        )
        set_user_role(cls.other_buyer, CLIENT)

        cls.worker = User.objects.create_user(
            username="crud_worker"
        )
        set_user_role(cls.worker, EMPLOYEE)

        category = Category.objects.create(name="CRUD API")
        cls.service = Service.objects.create(
            category=category,
            name="Услуга CRUD",
            price=Decimal("100.00"),
        )

    def setUp(self):
        self.order = save_order(
            Order(
                client=self.customer,
                service=self.service,
                desired_date=(
                    timezone.localdate() + timedelta(days=1)
                ),
                quantity=1,
            ),
            actor=self.buyer,
        )

    def headers(self, user=None):
        user = user or self.buyer
        token = signing.dumps(
            {"user_id": user.pk},
            salt=TOKEN_SALT,
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def post_update(self, data, user=None):
        return self.client.post(
            f"/api/orders/{self.order.pk}/update/",
            data,
            content_type="application/json",
            **self.headers(user),
        )

    def test_list_keeps_existing_response_format(self):
        response = self.client.get(
            "/api/orders/",
            **self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["orders"][0]
        self.assertEqual(item["id"], self.order.pk)
        self.assertEqual(item["service"], self.service.name)
        self.assertTrue(item["can_edit"])
        self.assertTrue(item["can_delete"])

    def test_detail(self):
        response = self.client.get(
            f"/api/orders/{self.order.pk}/",
            **self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["order"]["number"],
            self.order.order_number,
        )

    def test_update_recalculates_price(self):
        response = self.post_update(
            {"quantity": 3, "comment": "Изменено клиентом"}
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(
            self.order.total_price,
            Decimal("300.00"),
        )
        self.assertEqual(
            self.order.comment,
            "Изменено клиентом",
        )
        self.assertEqual(self.order.status_history.count(), 1)

    def test_invalid_quantity_rejected(self):
        for quantity in (0, 101, 1.5, True, "2"):
            with self.subTest(quantity=quantity):
                response = self.post_update({"quantity": quantity})
                self.assertEqual(response.status_code, 400)

        self.order.refresh_from_db()
        self.assertEqual(self.order.quantity, 1)

    def test_client_cannot_change_service_fields(self):
        for data in [
            {"status": Order.Status.READY},
            {"total_price": "1.00"},
            {"client_id": 999},
            {"employee_id": 999},
            {"employee_comment": "Подмена"},
        ]:
            with self.subTest(data=data):
                response = self.post_update(data)
                self.assertEqual(response.status_code, 400)

    def test_foreign_order_hidden_and_protected(self):
        response = self.client.get(
            f"/api/orders/{self.order.pk}/",
            **self.headers(self.other_buyer),
        )
        self.assertEqual(response.status_code, 404)

        response = self.post_update(
            {"quantity": 2},
            user=self.other_buyer,
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f"/api/orders/{self.order.pk}/delete/",
            **self.headers(self.other_buyer),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Order.objects.filter(pk=self.order.pk).exists()
        )

    def test_delete_is_real_and_requires_post(self):
        url = f"/api/orders/{self.order.pk}/delete/"

        response = self.client.get(url, **self.headers())
        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            Order.objects.filter(pk=self.order.pk).exists()
        )

        response = self.client.post(url, **self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertFalse(
            Order.objects.filter(pk=self.order.pk).exists()
        )

    def test_accepted_order_cannot_be_changed_or_deleted(self):
        self.order.status = Order.Status.ACCEPTED
        save_order(self.order, actor=self.worker)

        response = self.post_update({"quantity": 2})
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            f"/api/orders/{self.order.pk}/delete/",
            **self.headers(),
        )
        self.assertEqual(response.status_code, 403)

        detail = self.client.get(
            f"/api/orders/{self.order.pk}/",
            **self.headers(),
        ).json()["order"]

        self.assertFalse(detail["can_edit"])
        self.assertFalse(detail["can_delete"])

    def test_filter(self):
        response = self.client.get(
            "/api/orders/",
            {"status": Order.Status.READY},
            **self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["orders"], [])

    def test_sort(self):
        second = save_order(
            Order(
                client=self.customer,
                service=self.service,
                desired_date=self.order.desired_date,
                quantity=3,
            ),
            actor=self.buyer,
        )

        response = self.client.get(
            "/api/orders/",
            {"sort": "-total_price"},
            **self.headers(),
        )

        self.assertEqual(
            [item["id"] for item in response.json()["orders"]],
            [second.pk, self.order.pk],
        )

    def test_list_does_not_include_foreign_orders(self):
        response = self.client.get(
            "/api/orders/",
            **self.headers(self.other_buyer),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["orders"], [])

    def test_bad_sort_and_status(self):
        for params in [
            {"sort": "client__user__password"},
            {"status": "unknown"},
        ]:
            response = self.client.get(
                "/api/orders/",
                params,
                **self.headers(),
            )
            self.assertEqual(response.status_code, 400)

    def test_without_token(self):
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, 401)

    def test_employee_cannot_use_client_api(self):
        response = self.client.get(
            "/api/orders/",
            **self.headers(self.worker),
        )
        self.assertEqual(response.status_code, 403)

    def test_past_new_date_rejected(self):
        response = self.post_update({
            "desired_date": (
                timezone.localdate() - timedelta(days=1)
            ).isoformat()
        })
        self.assertEqual(response.status_code, 400)
