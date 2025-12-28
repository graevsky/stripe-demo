from __future__ import annotations

from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

"""
Модели сервиса.

Структура
- Item -- товар (имя, описание, цена, валюта)
- Order -- заказ из нескольких товаров
- OrderItem -- промежуточная модель между item и Order
- Discount / Tax -- сущности в Django, которые привязываются к Order
  и содержат ссылки на Stripe объекты через ID

- В Stripe расчет суммы после скидок и налогов делается в Checkout форме. total\subtotal используются для админ панели
"""


class Item(models.Model):
    """
    Класс товара.

    Валюта хранится в паре. Lowercase для Stripe, uppercase для отображения
    """

    CURRENCY_USD = "usd"
    CURRENCY_EUR = "eur"

    CURRENCY_CHOICES = [
        (CURRENCY_USD, "USD"),
        (CURRENCY_EUR, "EUR"),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=CURRENCY_USD,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.price} {self.currency.upper()})"


class Tax(models.Model):
    """
    Класс для налога

    - stripe_tax_rate_id - ID налога из Stripe (вида txr_***).
    - percentage/inclusive - поля используются для отображения в админ панели. Stripe сам считает сумму в Checkout
    """

    name = models.CharField(max_length=255)
    stripe_tax_rate_id = models.CharField(max_length=255, blank=True)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    inclusive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Discount(models.Model):
    """
    Класс для скидки

    - stripe_coupon_id - ID скидки из Stripe (вида TLA7****). Checkout поддерживает максимум одну скидку.
    - percent_off - для отображения.
    """

    name = models.CharField(max_length=255)
    stripe_coupon_id = models.CharField(max_length=255, blank=True)
    percent_off = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )

    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Order(models.Model):
    """
    Класс для заказа

    - items - ManyToMany через OrderItem
    - discounts/taxes - ManyToMany к Discount/Tax.
    """

    items = models.ManyToManyField(Item, through="OrderItem", related_name="orders")
    discounts = models.ManyToManyField(Discount, blank=True, related_name="orders")
    taxes = models.ManyToManyField(Tax, blank=True, related_name="orders")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Order #{self.pk}"

    def subtotal(self) -> Decimal:
        # Сумма без скидок\наллогов
        tot = Decimal("0.00")
        for ord_item in self.order_items.select_related("item").all():
            tot += ord_item.item.price * ord_item.quantity
        return tot

    def total_price(self):
        # Сумма со скидками\налогами
        # Stripe не использует, ужна для визуализации
        total = self.subtotal()

        for discount in self.discounts.filter(is_active=True):
            if discount.percent_off:
                total -= total * discount.percent_off / Decimal("100.00")
        for tax in self.taxes.filter(is_active=True):
            if tax.percentage is not None:
                total += total * tax.percentage / Decimal("100.00")

        return total.quantize(Decimal("0.01"))


class OrderItem(models.Model):
    """
    Класс для позиций в заказе
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="order_items",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "item"], name="uniq_order_item"),
        ]

    def __str__(self) -> str:
        return f"Order #{self.order_id}: {self.item.name} x {self.quantity}"
