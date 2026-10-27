from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login, get_user_model
from django.shortcuts import render
from django.db.models import Q
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from requests import get
from yaml import SafeLoader
from yaml import load as yaml_load
from .models import (
    ProductInfo, Order, OrderItem, Contact, Shop, Category, Product, Parameter, ProductParameter,
    ConfirmEmailToken
)
from .serializers import ProductInfoSerializer, UserSerializer, ContactSerializer, OrderSerializer
from .tasks import send_order_confirmation_task, send_invoice_to_admin_task

User = get_user_model()


# Список товаров с поиском и фильтрацией.
class ProductListView(generics.ListAPIView):
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = ProductInfo.objects.filter(quantity__gt=0, shop__state=True).prefetch_related('product_parameters')

        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(Q(product__name__icontains=search))

        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(product__category__name__icontains=category)

        shop = self.request.query_params.get('shop', None)
        if shop:
            queryset = queryset.filter(shop__name__icontains=shop)

        return queryset


# Детали одного товара.
class ProductDetailView(generics.RetrieveAPIView):
    queryset = ProductInfo.objects.all()
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]


# Регистрация.
class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


# Подтверждение регистрации по email.
class ConfirmRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token_key = request.data.get('token')
        if not token_key:
            return Response({"error": "Токен не указан"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = ConfirmEmailToken.objects.get(key=token_key)
        except ConfirmEmailToken.DoesNotExist:
            return Response({"error": "Неверный токен"}, status=status.HTTP_400_BAD_REQUEST)

        user = token.user
        user.is_active = True
        user.save()
        token.delete()

        return Response({"message": "Аккаунт подтверждён"})


# Логин (по email или username). Возвращает токен.
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        login_field = request.data.get('email') or request.data.get('username')
        password = request.data.get('password')

        if not login_field or not password:
            return Response({"error": "Укажите email/username и пароль"}, status=status.HTTP_400_BAD_REQUEST)

        # Пробуем найти по email, потом по username
        user = User.objects.filter(email=login_field).first() or User.objects.filter(username=login_field).first()

        if user is None:
            return Response({"error": "Неверный логин или пароль"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({"error": "Аккаунт не подтверждён. Проверьте почту."}, status=status.HTTP_403_FORBIDDEN)

        user = authenticate(request, username=user.username, password=password)
        if user is not None:
            login(request, user)
            from rest_framework.authtoken.models import Token
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"message": "Успешный вход", "username": user.username, "token": token.key})
        else:
            return Response({"error": "Неверный логин или пароль"}, status=status.HTTP_401_UNAUTHORIZED)


# Корзина.
class CartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        order, _ = Order.objects.get_or_create(user=request.user, state='basket')
        items = order.ordered_items.all()
        data = [{"id": item.id, "product_info": item.product_info.product.name, "quantity": item.quantity, "price": item.product_info.price} for item in items]
        total = sum(item.product_info.price * item.quantity for item in items)
        return Response({"cart_items": data, "total": total})

    def post(self, request):
        order, _ = Order.objects.get_or_create(user=request.user, state='basket')
        product_info_id = request.data.get('product_info_id')
        quantity = int(request.data.get('quantity', 1))

        try:
            product_info = ProductInfo.objects.get(id=product_info_id, quantity__gt=0)
        except ProductInfo.DoesNotExist:
            return Response({"error": "Товар не найден"}, status=status.HTTP_404_NOT_FOUND)

        # Ищем существующую позицию или создаём новую с quantity
        order_item, created = OrderItem.objects.get_or_create(
            order=order,
            product_info=product_info,
            defaults={'quantity': quantity}  # <-- ДОБАВИЛИ
        )
        if not created:
            order_item.quantity += quantity
        order_item.save()

        return Response({"message": "Товар добавлен в корзину"}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        order = Order.objects.filter(user=request.user, state='basket').first()
        if not order:
            return Response({"error": "Корзина пуста"}, status=status.HTTP_404_NOT_FOUND)

        product_info_id = request.data.get('product_info_id')

        try:
            order_item = OrderItem.objects.get(order=order, product_info_id=product_info_id)
            order_item.delete()
            return Response({"message": "Товар удалён из корзины"}, status=status.HTTP_200_OK)
        except OrderItem.DoesNotExist:
            return Response({"error": "Товар не найден в корзине"}, status=status.HTTP_404_NOT_FOUND)


# Контакты.
class ContactView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contacts = Contact.objects.filter(user=request.user)
        serializer = ContactSerializer(contacts, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, contact_id):
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
            contact.delete()
            return Response({"message": "Контакт удалён"}, status=status.HTTP_200_OK)
        except Contact.DoesNotExist:
            return Response({"error": "Контакт не найден"}, status=status.HTTP_404_NOT_FOUND)


# Заказы.
class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        contact_id = request.data.get('contact_id')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
        except Contact.DoesNotExist:
            return Response({"error": "Адрес не найден"}, status=status.HTTP_404_NOT_FOUND)

        order = Order.objects.filter(user=request.user, state='basket').first()
        if not order or not order.ordered_items.exists():
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        order.state = 'new'
        order.contact = contact
        order.save()

        items_data = []
        for item in order.ordered_items.all():
            items_data.append({
                "product": item.product_info.product.name,
                "quantity": item.quantity,
                "price": str(item.product_info.price)
            })

        user_email = request.user.email
        if user_email:
            send_order_confirmation_task.delay(user_email, order.id, items_data)

        send_invoice_to_admin_task.delay(order.id, items_data, request.user.username)

        return Response({"message": "Заказ оформлен", "order_id": order.id}, status=status.HTTP_201_CREATED)

    def get(self, request):
        orders = Order.objects.filter(user=request.user).exclude(state='basket').order_by('-dt')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


# Детали заказа.
class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).exclude(state='basket')


# Обновление статуса заказа (для админа/поставщика).
class OrderStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Заказ не найден"}, status=status.HTTP_404_NOT_FOUND)

        new_state = request.data.get('state')
        if new_state in dict(Order.STATUS_CHOICES):
            order.state = new_state
            order.save()
            return Response({"message": "Статус обновлён", "state": order.state})
        return Response({"error": "Неверный статус"}, status=status.HTTP_400_BAD_REQUEST)


# Обновление прайса поставщиком.
class PartnerUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return Response({'Status': False, 'Error': str(e)}, status=400)
            else:
                stream = get(url).content
                data = yaml_load(stream, Loader=SafeLoader)

                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)

                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)

                ProductInfo.objects.filter(shop_id=shop.id).delete()

                for item in data['goods']:
                    product, _ = Product.objects.update_or_create(
                        name=item['name'],
                        category_id=item['category'],
                        defaults={'description': item.get('description', '')}
                    )
                    product_info = ProductInfo.objects.create(
                        product_id=product.id,
                        external_id=item['id'],
                        model=item['model'],
                        price=item['price'],
                        price_rrc=item['price_rrc'],
                        quantity=item['quantity'],
                        shop_id=shop.id
                    )
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(
                            product_info_id=product_info.id,
                            parameter_id=parameter_object.id,
                            value=value
                        )

                return Response({'Status': True})
        return Response({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'}, status=400)


# Заказы поставщика.
class PartnerOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            shop = Shop.objects.get(user=request.user)
        except Shop.DoesNotExist:
            return Response({"error": "У вас нет магазина"}, status=status.HTTP_404_NOT_FOUND)

        orders = Order.objects.filter(
            ordered_items__product_info__shop=shop
        ).exclude(state='basket').distinct().order_by('-dt')

        data = []
        for order in orders:
            items = order.ordered_items.filter(product_info__shop=shop)
            items_data = [{"product": i.product_info.product.name, "quantity": i.quantity, "price": i.product_info.price} for i in items]
            data.append({
                "order_id": order.id,
                "state": order.state,
                "dt": order.dt,
                "items": items_data
            })

        return Response(data)


# Визуальный каталог.
def catalog_view(request):
    products = ProductInfo.objects.filter(quantity__gt=0, shop__state=True).prefetch_related('product_parameters')
    return render(request, 'catalog.html', {'products': products})


# Главная страница.
def home_view(request):
    return render(request, 'home.html')