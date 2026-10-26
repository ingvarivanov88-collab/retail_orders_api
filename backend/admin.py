from django.contrib import admin
from .models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, Contact
from .tasks import send_status_update_task


# Регистрация модели магазина
@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'state')  # Показываем имя и статус
    list_filter = ('state',)                # Фильтр по статусу
    search_fields = ('name',)               # Поиск по названию


# Регистрация модели категории
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# Регистрация модели продукта
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)


# Inline для параметров товара (чтобы редактировать прямо в карточке товара)
class ProductParameterInline(admin.TabularInline):
    model = ProductParameter
    extra = 1  # Количество пустых строк для добавления


# Регистрация модели ProductInfo (конкретный товар в магазине)
@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'shop', 'price', 'quantity')
    list_filter = ('shop',)
    search_fields = ('product__name',)
    inlines = [ProductParameterInline]  # Параметры прямо в карточке


# Регистрация модели параметра (справочник)
@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# Регистрация модели заказа
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'state', 'dt')
    list_filter = ('state',)
    search_fields = ('user__username',)

    def save_model(self, request, obj, form, change):
        """При смене статуса заказа отправляем уведомление клиенту."""
        if change:
            old_obj = Order.objects.get(pk=obj.pk)
            if old_obj.state != obj.state:
                if obj.user.email:
                    send_status_update_task.delay(obj.user.email, obj.id, obj.get_state_display())
        super().save_model(request, obj, form, change)


# Регистрация модели позиции заказа
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product_info', 'quantity')
    search_fields = ('order__id', 'product_info__product__name')


# Регистрация модели контакта (адрес доставки)
@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'city', 'street', 'house', 'phone')
    search_fields = ('user__username', 'city')