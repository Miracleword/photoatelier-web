from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import (
    Category,
    Client,
    Notification,
    Order,
    Service,
    StatusHistory,
)
from .order_actions import save_order
from .roles import (
    CLIENT,
    EMPLOYEE,
    ensure_role_groups,
    set_user_role,
)


class OrderActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        ensure_role_groups()

        cls.worker = User.objects.create_user(username="action_worker")
        set_user_role(cls.worker, EMPLOYEE)

        cls.buyer = User.objects.create_user(username="action_buyer")
        set_user_role(cls.buyer, CLIENT)
        cls.customer = Client.objects.get(user=cls.buyer)

        cls.other_buyer = User.objects.create_user(
            username="action_other_buyer"
        )
        set_user_role(cls.other_buyer, CLIENT)

        category = Category.objects.create(name="Тест действий")
        cls.service = Service.objects.create(
            category=category,
            name="Тестовая услуга действий",
            price=Decimal("100.00"),
        )

    def draft(self):
        return Order(
            client=self.customer,
            service=self.service,
            desired_date=timezone.localdate() + timedelta(days=1),
            quantity=1,
        )

    def test_client_creation(self):
        order = save_order(self.draft(), actor=self.buyer)
        self.assertEqual(order.total_price, Decimal("100.00"))
        self.assertIsNone(order.employee_id)
        self.assertEqual(order.status_history.count(), 1)
        self.assertEqual(order.notifications.count(), 1)
        self.assertIsNone(order.status_history.get().employee_id)

    def test_worker_status_has_author(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.status = Order.Status.ACCEPTED
        save_order(order, actor=self.worker)

        last = order.status_history.order_by("-pk").first()
        self.assertEqual(
            last.employee_id,
            self.worker.employee_profile.pk,
        )
        self.assertEqual(
            order.employee_id,
            self.worker.employee_profile.pk,
        )
        self.assertEqual(order.status_history.count(), 2)
        self.assertEqual(order.notifications.count(), 2)

    def test_comment_edit_does_not_duplicate_status(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.employee_comment = "Уточнение сотрудника"
        save_order(order, actor=self.worker)

        self.assertEqual(order.status_history.count(), 1)
        self.assertEqual(order.notifications.count(), 1)

    def test_status_preserves_historical_price(self):
        order = save_order(self.draft(), actor=self.buyer)

        Order.objects.filter(pk=order.pk).update(
            total_price=Decimal("150.00")
        )
        order.refresh_from_db()
        order.status = Order.Status.ACCEPTED
        save_order(order, actor=self.worker)

        self.assertEqual(order.total_price, Decimal("150.00"))

    def test_quantity_change_recalculates_price(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.quantity = 3
        save_order(order, actor=self.worker)
        self.assertEqual(order.total_price, Decimal("300.00"))

    def test_second_worker_does_not_replace_responsible(self):
        order = save_order(self.draft(), actor=self.worker)

        another_worker = get_user_model().objects.create_user(
            username="second_action_worker"
        )
        set_user_role(another_worker, EMPLOYEE)

        order.status = Order.Status.ACCEPTED
        save_order(order, actor=another_worker)

        self.assertEqual(
            order.employee_id,
            self.worker.employee_profile.pk,
        )
        self.assertEqual(
            order.status_history.order_by("-pk").first().employee_id,
            another_worker.employee_profile.pk,
        )

    def test_other_client_cannot_save_order(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.comment = "Чужое изменение"

        with self.assertRaises(PermissionDenied):
            save_order(order, actor=self.other_buyer)

    def test_client_cannot_change_status(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.status = Order.Status.READY

        with self.assertRaises(PermissionDenied):
            save_order(order, actor=self.buyer)

    def test_client_cannot_edit_accepted_order(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.status = Order.Status.ACCEPTED
        save_order(order, actor=self.worker)

        order.comment = "Поздняя правка"
        with self.assertRaises(ValidationError):
            save_order(order, actor=self.buyer)

    def test_zero_quantity_rejected(self):
        order = self.draft()
        order.quantity = 0
        with self.assertRaises(ValidationError):
            save_order(order, actor=self.buyer)
        self.assertEqual(Order.objects.count(), 0)

    def test_cancellation_requires_reason(self):
        order = save_order(self.draft(), actor=self.buyer)
        order.status = Order.Status.CANCELLED

        with self.assertRaises(ValidationError):
            save_order(order, actor=self.worker)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_failure_rolls_back_all_changes(self):
        with patch(
            "studio.order_actions.Notification.objects.create",
            side_effect=RuntimeError("Искусственная ошибка"),
        ):
            with self.assertRaises(RuntimeError):
                save_order(self.draft(), actor=self.buyer)

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StatusHistory.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_api_creation_uses_same_rules(self):
        from django.core import signing
        from .api import TOKEN_SALT

        token = signing.dumps(
            {"user_id": self.buyer.pk},
            salt=TOKEN_SALT,
        )
        response = self.client.post(
            "/api/orders/create/",
            {
                "service_id": self.service.pk,
                "quantity": 2,
                "desired_date": (
                    timezone.localdate() + timedelta(days=1)
                ).isoformat(),
                "comment": "Тест API",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.json()["id"])
        self.assertEqual(order.total_price, Decimal("200.00"))
        self.assertEqual(order.status_history.count(), 1)
        self.assertEqual(order.notifications.count(), 1)
