from django.contrib import admin
from shop.models import Item, OrderItem, Order, Discount, Tax

"""
Админ панель Django для управления магазином

Возможности админки:
- Создавать Item, Tax, Discount
- Создавать Order используя Item, скидки и налоги

Важно: tax и discout требуют добавления в stripe
"""


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    """
    Панель для Item.
    Поддерживает поиск по имени, фильтры по валютам и датам создания. Сортировка по датам от новых к старым.
    """

    list_display = ("id", "name", "price", "currency", "created_at")
    search_fields = ("name",)
    list_filter = ("currency", "created_at")
    ordering = ("-created_at",)


class OrderItemInline(admin.TabularInline):
    """
    Inline для редактирования ордеров. Работает на основе Item, поддерживает автодополнение имени item.
    """

    model = OrderItem
    extra = 0
    autocomplete_fields = ("item",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    Панель для заказов.

    - Содержимое Item можно редактировать прямо в заказе.
    - Фильтры (+применение) по налогам и скидкам
    - Подсчитывает сумму до налогов, скидок (subtotal) и после (total)
    """

    list_display = ("id", "created_at", "subtotal_display", "total_display")
    inlines = (OrderItemInline,)
    filter_horizontal = ("discounts", "taxes")
    ordering = ("-created_at",)

    def subtotal_display(self, obj: Order):
        # Подсчет суммы заказа до скидок\налогов
        return obj.subtotal()

    subtotal_display.short_description = "Subtotal"

    def total_display(self, obj: Order):
        # Подсчет суммы заказа с налогами\скидками
        return obj.total_price()

    total_display.short_description = "Total"


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    """
    Панель для скидок.

    - stripe_coupon_id - ID скидки из Stripe. Можно получить в dashboard stripe при созаднии скидки. Пример: TLA7****

    - is_active - позволяет выключать скидку без удаления.
    """

    list_display = ("id", "name", "stripe_coupon_id", "percent_off", "is_active")
    search_fields = ("name", "stripe_coupon_id")
    list_filter = ("is_active",)

    search_fields = ("name", "stripe_coupon_id")
    list_filter = ("is_active",)
    ordering = ("name",)

    def get_queryset(self, request):
        # Порядок сортировке, который сначала отображает активные скидки.
        qs = super().get_queryset(request)
        return qs.order_by("-is_active", "name")


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    """
    Панель для налогов.

    - stripe_tax_rate_id - ID налога из Stripe (вида txr_***), который затем передаётся в line_items[].tax_rates. Для создания utils/create_tax.py
    - inclusive - флаг для админ панели, на работу Stripe не влияет (тип выставляется при создании налога)
    """

    list_display = (
        "id",
        "name",
        "stripe_tax_rate_id",
        "percentage",
        "inclusive",
        "is_active",
    )
    search_fields = ("name", "stripe_tax_rate_id")
    list_filter = ("inclusive", "is_active")
    ordering = ("name",)

    def get_queryset(self, request):
        # Порядок сортировке, который сначала отображает активные налоги.
        qs = super().get_queryset(request)
        return qs.order_by("-is_active", "name")
