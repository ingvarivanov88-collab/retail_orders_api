from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login, get_user_model
from django.shortcuts import render
from django.db.models import Q
from django.db import transaction
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from requests import get, RequestException
import yaml
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
        items = order.ordered_items.select_related(
            'product_info__product',
            'product_info__shop'
        )

        data = []
        total = 0

        for item in items:
            price = item.product_info.price
            item_total = price * item.quantity
            total += item_total

            data.append({
                "id": item.id,
                "product_info_id": item.product_info_id,
                "product": item.product_info.product.name,
                "shop": item.product_info.shop.name,
                "quantity": item.quantity,
                "price": price,
                "sum": item_total,
            })

        return Response({"cart_items": data, "total": total})

    def post(self, request):
        product_info_id = request.data.get('product_info_id')
        raw_quantity = request.data.get('quantity', 1)

        if isinstance(raw_quantity, bool) or not str(raw_quantity).isdigit():
            return Response(
                {"error": "Количество должно быть целым числом"},
                status=status.HTTP_400_BAD_REQUEST
            )

        quantity = int(raw_quantity)

        if quantity <= 0:
            return Response(
                {"error": "Количество должно быть больше нуля"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            product_info = (
                ProductInfo.objects.select_for_update()
                .filter(id=product_info_id, shop__state=True)
                .first()
            )

            if product_info is None:
                return Response(
                    {"error": "Товар не найден или недоступен"},
                    status=status.HTTP_404_NOT_FOUND
                )

            order, _ = Order.objects.get_or_create(
                user=request.user,
                state='basket'
            )

            order_item = OrderItem.objects.filter(
                order=order,
                product_info=product_info
            ).first()

            current_quantity = order_item.quantity if order_item else 0
            total_quantity = current_quantity + quantity

            if total_quantity > product_info.quantity:
                return Response(
                    {"error": (
                        f"На складе {product_info.quantity} шт., "
                        f"в корзине уже {current_quantity} шт."
                    )},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if order_item:
                order_item.quantity = total_quantity
                order_item.save(update_fields=['quantity'])
            else:
                OrderItem.objects.create(
                    order=order,
                    product_info=product_info,
                    quantity=quantity
                )

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

        contact = Contact.objects.filter(
            id=contact_id,
            user=request.user
        ).first()

        if contact is None:
            return Response(
                {"error": "Адрес доставки не найден"},
                status=status.HTTP_404_NOT_FOUND
            )

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .filter(user=request.user, state='basket')
                .first()
            )

            if order is None:
                return Response(
                    {"error": "Корзина пуста"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            order_items = list(order.ordered_items.all())

            if not order_items:
                return Response(
                    {"error": "В корзине нет товаров"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            stock_updates = []
            items_data = []

            for item in order_items:
                product_info = (
                    ProductInfo.objects.select_for_update()
                    .select_related('product', 'shop')
                    .get(id=item.product_info_id)
                )

                if not product_info.shop.state:
                    return Response(
                        {"error": (
                            f"Магазин {product_info.shop.name} "
                            "не принимает заказы"
                        )},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if item.quantity > product_info.quantity:
                    return Response(
                        {"error": (
                            f"Недостаточно товара: "
                            f"{product_info.product.name}. "
                            f"Доступно: {product_info.quantity}"
                        )},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                stock_updates.append((product_info, item.quantity))
                items_data.append({
                    "product": product_info.product.name,
                    "quantity": item.quantity,
                    "price": str(product_info.price)
                })

            for product_info, quantity in stock_updates:
                product_info.quantity -= quantity
                product_info.save(update_fields=['quantity'])

            order.state = 'new'
            order.contact = contact
            order.save(update_fields=['state', 'contact'])

            order_id = order.id
            user_email = request.user.email
            username = request.user.username

            def send_notifications():
                if user_email:
                    send_order_confirmation_task.delay(
                        user_email, order_id, items_data
                    )
                send_invoice_to_admin_task.delay(
                    order_id, items_data, username
                )

            transaction.on_commit(send_notifications)

        return Response(
            {"message": "Заказ оформлен", "order_id": order_id},
            status=status.HTTP_201_CREATED
        )

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


# Обновление статуса заказа.
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

        if not url:
            return Response(
                {"error": "Укажите URL прайс-листа"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            URLValidator()(url)

            response = get(url, timeout=15)
            response.raise_for_status()

            data = yaml.safe_load(response.content)

            if not isinstance(data, dict):
                raise ValueError("Неверная структура YAML")

            if not data.get('shop'):
                raise ValueError("Не указано название магазина")

            if not isinstance(data.get('categories'), list):
                raise ValueError("Отсутствует список категорий")

            if not isinstance(data.get('goods'), list):
                raise ValueError("Отсутствует список товаров")

            with transaction.atomic():
                shop, _ = Shop.objects.get_or_create(
                    user=request.user,
                    defaults={'name': data['shop']}
                )

                if shop.name != data['shop']:
                    shop.name = data['shop']
                    shop.save(update_fields=['name'])

                category_map = {}

                for cat_data in data['categories']:
                    category = Category.objects.filter(
                        name=cat_data['name']
                    ).first()

                    if category is None:
                        category = Category.objects.create(
                            name=cat_data['name']
                        )

                    category.shops.add(shop)
                    category_map[cat_data['id']] = category

                for item in data['goods']:
                    category = category_map.get(item['category'])

                    if category is None:
                        raise ValueError(
                            f"Категория {item['category']} "
                            "отсутствует в прайс-листе"
                        )

                    product, _ = Product.objects.update_or_create(
                        name=item['name'],
                        category=category,
                        defaults={
                            'description': item.get('description', '')
                        }
                    )

                    product_info, _ = ProductInfo.objects.update_or_create(
                        external_id=item['id'],
                        product=product,
                        shop=shop,
                        defaults={
                            'model': item.get('model', ''),
                            'price': item['price'],
                            'price_rrc': item.get(
                                'price_rrc', item['price']
                            ),
                            'quantity': item.get('quantity', 0),
                        }
                    )

                    for name, value in item.get('parameters', {}).items():
                        parameter, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.update_or_create(
                            product_info=product_info,
                            parameter=parameter,
                            defaults={'value': str(value)}
                        )

            return Response({
                "Status": True,
                "message": "Прайс-лист обновлён"
            })

        except (
            ValidationError,
            RequestException,
            yaml.YAMLError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            return Response(
                {"Status": False, "error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )


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


# Переключение приёма заказов поставщиком.
class PartnerStateUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        shop = Shop.objects.filter(user=request.user).first()

        if shop is None:
            return Response({"error": "У вас нет магазина"}, status=status.HTTP_404_NOT_FOUND)

        new_state = request.data.get('state')

        if isinstance(new_state, bool):
            state = new_state
        elif isinstance(new_state, str):
            value = new_state.strip().lower()
            if value not in ('true', 'false'):
                return Response(
                    {"error": "state должно быть true или false"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            state = value == 'true'
        else:
            return Response(
                {"error": "state должно быть true или false"},
                status=status.HTTP_400_BAD_REQUEST
            )

        shop.state = state
        shop.save(update_fields=['state'])

        return Response({"message": "Статус приёма заказов обновлён", "state": shop.state})


# Визуальный каталог.
def catalog_view(request):
    products = ProductInfo.objects.filter(quantity__gt=0, shop__state=True).prefetch_related('product_parameters')
    return render(request, 'catalog.html', {'products': products})


# Главная страница.
def home_view(request):
    return render(request, 'home.html')