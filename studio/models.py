from django.conf import settings
from django.db import models


class Client(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
    )
    full_name = models.CharField("ФИО", max_length=150)
    phone = models.CharField("Телефон", max_length=30)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self):
        return self.full_name


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    full_name = models.CharField("ФИО", max_length=150)
    position = models.CharField("Должность", max_length=100, default="Сотрудник")

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

    def __str__(self):
        return self.full_name


class Category(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Категория услуг"
        verbose_name_plural = "Категории услуг"

    def __str__(self):
        return self.name


class ServiceFormat(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Формат услуги"
        verbose_name_plural = "Форматы услуг"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Service(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name="Категория",
    )
    service_format = models.ForeignKey(
        ServiceFormat,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="services",
        verbose_name="Формат услуги",
    )
    name = models.CharField("Название", max_length=150)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Цена, ₽", max_digits=10, decimal_places=2)
    estimated_days = models.PositiveIntegerField("Срок выполнения, дней", default=1)
    is_active = models.BooleanField("Доступна для заказа", default=True)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="studio_service_price_nonnegative",
            ),
        ]

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        ACCEPTED = "accepted", "Принят"
        IN_PROGRESS = "in_progress", "В работе"
        READY = "ready", "Готов"
        ISSUED = "issued", "Выдан"
        CANCELLED = "cancelled", "Отменён"

    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Клиент",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Услуга",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Сотрудник",
    )
    desired_date = models.DateField("Желаемая дата")
    quantity = models.PositiveIntegerField("Количество", default=1)
    total_price = models.DecimalField(
        "Стоимость, ₽",
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    comment = models.TextField("Комментарий клиента", blank=True)
    employee_comment = models.TextField("Комментарий сотрудника", blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=100),
                name="studio_order_quantity_1_100",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name="studio_order_total_nonnegative",
            ),
        ]

    @property
    def order_number(self):
        return f"ЗК-{self.pk:05d}" if self.pk else "Новый заказ"

    def __str__(self):
        return self.order_number


class StatusHistory(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="Заказ",
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Order.Status.choices,
    )
    comment = models.TextField("Комментарий", blank=True)
    changed_at = models.DateTimeField("Дата изменения", auto_now_add=True)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Сотрудник",
    )

    class Meta:
        verbose_name = "Запись истории статуса"
        verbose_name_plural = "История статусов"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.order.order_number}: {self.get_status_display()}"


class Notification(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Клиент",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Заказ",
    )
    text = models.CharField("Текст", max_length=255)
    is_read = models.BooleanField("Прочитано", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]

    def __str__(self):
        return self.text