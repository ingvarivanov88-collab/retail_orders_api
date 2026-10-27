from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Shop, Category, Product, ProductInfo, Parameter, ProductParameter,
    Order, OrderItem, Contact
)
from .tasks import send_status_update_task


# Регистрация кастомной модели User (чтобы появился раздел "Пользователи")
admin.site.register(User, UserAdmin)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'state')
    list_filter = ('state',)
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)


class ProductParameterInline(admin.TabularInline):
    model = ProductParameter
    extra = 1


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'shop', 'price', 'quantity')
    list_filter = ('shop',)
    search_fields = ('product__name',)
    inlines = [ProductParameterInline]


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


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


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product_info', 'quantity')
    search_fields = ('order__id', 'product_info__product__name')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'city', 'street', 'house', 'phone')
    search_fields = ('user__username', 'city')