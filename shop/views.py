from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Item, Order, OrderItem

"""
Представления для сервиса.

Поддерживаются:
- /item/{id}: страница товара
- /buy/{id}: Checkout Session + session.id
- /order/{id}: страница заказа
- /buy-order/{id}: Checkout Session на содержимое заказа
"""

stripe.api_key = settings.STRIPE_SECRET_KEY


def _amount_to_cents(amount: Decimal) -> int:
    # Округление для .xx в цене.
    if amount is None:
        raise ValueError("amount is required")

    normalized = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(normalized)


def _build_return_urls(request, detail_view_name: str, kwargs: dict) -> tuple[str, str]:
    # Создание success_url\cancel_url для checkout.
    base = request.build_absolute_uri(reverse(detail_view_name, kwargs=kwargs))
    return f"{base}?success=1", f"{base}?canceled=1"


def _stripe_error_response(exc: Exception) -> JsonResponse:
    message = getattr(exc, "user_message", None) or str(exc) or "Stripe error"
    return JsonResponse({"error": message}, status=400)


@require_GET
def item_detail(request, item_id: int):
    # GET /item/id - отображение товара+кнопка купить
    item = get_object_or_404(Item, pk=item_id)
    return render(
        request,
        "shop/item_detail.html",
        {
            "item": item,
            "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
        },
    )


@require_GET
def buy_item(request, item_id: int):
    """
    Создание checkout session для одного товара.
    Возвращает session.id

    Налоги и скидки не применяются, они только для ордеров
    """
    item = get_object_or_404(Item, pk=item_id)
    success_url, cancel_url = _build_return_urls(
        request, "item_detail", {"item_id": item.id}
    )

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            # line_items - отображение товаров в форме чекаута
            line_items=[
                {
                    "price_data": {
                        "currency": item.currency,
                        "product_data": {
                            "name": item.name,
                            "description": (item.description or "")[:500],
                        },
                        "unit_amount": _amount_to_cents(item.price),
                    },
                    "quantity": 1,
                }
            ],
        )
    except stripe.error.StripeError as exc:
        return _stripe_error_response(exc)

    return JsonResponse({"id": session.id})


@require_GET
def order_detail(request, order_id: int):
    """
    Отображение для заказа

    - Отображает список item и кнопку купить
    """
    order = get_object_or_404(Order, pk=order_id)

    order_items = (
        OrderItem.objects.select_related("item").filter(order=order).order_by("id")
    )
    if not order_items.exists():
        raise Http404("Order has no items")

    # Валюта заказа на основе первого item. Несколько валют в заказе не поддерживаются
    currency = order_items.first().item.currency

    return render(
        request,
        "shop/order_detail.html",
        {
            "order": order,
            "order_items": order_items,
            "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
            "currency": currency,
        },
    )


@require_GET
def buy_order(request, order_id: int):
    """
    "Покупка заказов", создает Checkout Session для заказа.

    - Поддерживается только 1 валюта на уровне заказа (глобально, поддерживаются USD\EUR)
    - Checkout поддерживает только 1 скидку на одну Session
    - Поддержка налогов
    """
    order = get_object_or_404(Order, pk=order_id)

    order_items = OrderItem.objects.select_related("item").filter(order=order)
    if not order_items.exists():
        raise Http404("Order has no items")

    # Валидация валют
    currency = order_items.first().item.currency
    if order_items.exclude(item__currency=currency).exists():
        return JsonResponse(
            {"error": "Mixed currencies in one order are not supported"},
            status=400,
        )

    # Поиск налогов
    tax_rate_ids = [
        t.stripe_tax_rate_id
        for t in order.taxes.filter(is_active=True).only("stripe_tax_rate_id")
        if t.stripe_tax_rate_id
    ]

    # Список item для заказа
    line_items = []
    for oi in order_items:
        item_data = {
            "price_data": {
                "currency": oi.item.currency,
                "product_data": {
                    "name": oi.item.name,
                    "description": (oi.item.description or "")[:500],
                },
                "unit_amount": _amount_to_cents(oi.item.price),
            },
            "quantity": oi.quantity,
        }

        if tax_rate_ids:
            item_data["tax_rates"] = tax_rate_ids

        line_items.append(item_data)

    # Поиск скидок
    active_discounts = list(
        order.discounts.filter(is_active=True).only("stripe_coupon_id")
    )
    coupon_ids = [d.stripe_coupon_id for d in active_discounts if d.stripe_coupon_id]

    if len(coupon_ids) > 1:
        return JsonResponse(
            {
                "error": (
                    "Stripe Checkout supports only one coupon/promotion code per session. "
                    "Leave only one active discount on the Order."
                )
            },
            status=400,
        )

    discounts_param = [{"coupon": coupon_ids[0]}] if coupon_ids else None

    success_url, cancel_url = _build_return_urls(
        request, "order_detail", {"order_id": order.id}
    )

    # Создание чекаута
    try:
        session_create_params = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items": line_items,
            "tax_id_collection": {"enabled": True},
        }
        if discounts_param:
            session_create_params["discounts"] = discounts_param

        session = stripe.checkout.Session.create(**session_create_params)
    except stripe.error.StripeError as exc:
        return _stripe_error_response(exc)

    return JsonResponse({"id": session.id})
