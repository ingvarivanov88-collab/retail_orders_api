from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from backend.views import (
    ProductListView, ProductDetailView, RegisterView, LoginView, CartView, OrderView, catalog_view, ContactView,
    PartnerUpdateView, home_view, OrderDetailView, OrderStatusUpdateView, PartnerOrdersView,
    ConfirmRegistrationView
)
from backend.views_import import import_products_view


def profile_view(request):
    return HttpResponse(
        "Вы успешно вошли в систему. Перейдите на <a href='/catalog/'>каталог</a> или в <a href='/api/cart/'>корзину</a>.")


urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('admin/import/', import_products_view, name='import-products'),
    path('api-auth/', include('rest_framework.urls')),
    path('api/password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    path('accounts/profile/', profile_view, name='profile'),
    path('catalog/', catalog_view, name='catalog'),
    path('api/products/', ProductListView.as_view(), name='product-list'),
    path('api/products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('api/register/', RegisterView.as_view(), name='register'),
    path('api/register/confirm/', ConfirmRegistrationView.as_view(), name='register-confirm'),  # <-- ДОБАВИЛИ
    path('api/login/', LoginView.as_view(), name='login'),
    path('api/cart/', CartView.as_view(), name='cart'),
    path('api/contacts/', ContactView.as_view(), name='contacts'),
    path('api/contacts/<int:contact_id>/', ContactView.as_view(), name='contact-detail'),
    path('api/orders/', OrderView.as_view(), name='orders'),
    path('api/orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('api/orders/<int:order_id>/status/', OrderStatusUpdateView.as_view(), name='order-status'),
    path('api/partner/update/', PartnerUpdateView.as_view(), name='partner-update'),
    path('api/partner/orders/', PartnerOrdersView.as_view(), name='partner-orders'),
]