from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login
from django.shortcuts import render
from django.db.models import Q
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from requests import get
from yaml import SafeLoader
from yaml import load as yaml_load
from .models import ProductInfo, Order, OrderItem, Contact, Shop, Category, Product, Parameter, ProductParameter
from .serializers import ProductInfoSerializer, UserSerializer, ContactSerializer, OrderSerializer
from .tasks import send_order_confirmation_task, send_invoice_to_admin_task


# Список товаров с поиском и фильтрацией.
# Сделал через ListAPIView, чтобы потом легко добавить пагинацию.
class ProductListView(generics.ListAPIView):
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # Фильтруем только активные магазины
        queryset = ProductInfo.objects.filter(quantity__gt=0, shop__state=True).prefetch_related('product_parameters')

        # Поиск по названию товара (например, ?search=iPhone)
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(Q(product__name__icontains=search))

        # Фильтр по категории (например, ?category=Смартфоны)
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(product__category__name__icontains=category)

        # Фильтр по магазину (например, ?shop=ТехноМир)
        shop = self.request.query_params.get('shop', None)
        if shop:
            queryset = queryset.filter(shop__name__icontains=shop)

        return queryset


# Детали одного товара.
class ProductDetailView(generics.RetrieveAPIView):
    queryset = ProductInfo.objects.all()
    serializer_class = ProductInfoSerializer
    permission_classes = [permissions.AllowAny]


# Регистрация. Использую стандартный CreateAPIView,
# а логику сохранения пользователя описал в UserSerializer.
class RegisterView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


# Логин. Возвращает токен для TokenAuthentication.
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            from rest_framework.authtoken.models import Token
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"message": "Успешный вход", "username": user.username, "token": token.key})
        else:
            return Response({"error": "Неверный логин или пароль"}, status=status.HTTP_401_UNAUTHORIZED)


# Корзина. Использую Order со статусом 'basket' — так проще,
# потому что при оформлении заказа нужно просто сменить статус, а не переносить товары.
class CartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Если корзины нет — создаём
        order, _ = Order.objects.get_or_create(user=request.user, state='basket')
        items = order.ordered_items.all()
        data = [{"id": item.id, "product_info": item.product_info.product.name, "quantity": item.quantity} for item in items]
        return Response({"cart_items": data})

    def post(self, request):
        order, _ = Order.objects.get_or_create(user=request.user, state='basket')
        product_info_id = request.data.get('product_info_id')
        quantity = int(request.data.get('quantity', 1))

        try:
            product_info = ProductInfo.objects.get(id=product_info_id, quantity__gt=0)
        except ProductInfo.DoesNotExist:
            return Response({"error": "Товар не найден"}, status=status.HTTP_404_NOT_FOUND)

        # Если товар уже в корзине — увеличиваем количество, иначе создаём новую строку
        order_item, created = OrderItem.objects.get_or_create(order=order, product_info=product_info)
        if not created:
            order_item.quantity += quantity
        else:
            order_item.quantity = quantity
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


# Контакты. Сделал один view на все операции: GET (список), POST (создать), DELETE (удалить).
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


# Заказы. POST — оформить заказ из корзины, GET — посмотреть список.
class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        contact_id = request.data.get('contact_id')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
        except Contact.DoesNotExist:
            return Response({"error": "Адрес не найден"}, status=status.HTTP_404_NOT_FOUND)

        # Находим корзину
        order = Order.objects.filter(user=request.user, state='basket').first()
        if not order or not order.ordered_items.exists():
            return Response({"error": "Корзина пуста"}, status=status.HTTP_400_BAD_REQUEST)

        # Меняем статус на "Новый" и привязываем контакт
        order.state = 'new'
        order.contact = contact
        order.save()

        # Собираем данные для писем
        items_data = []
        for item in order.ordered_items.all():
            items_data.append({
                "product": item.product_info.product.name,
                "quantity": item.quantity,
                "price": str(item.product_info.price)
            })

        # Отправляем письма через Celery (чтобы не тормозить ответ)
        user_email = request.user.email
        if user_email:
            send_order_confirmation_task.delay(user_email, order.id, items_data)

        send_invoice_to_admin_task.delay(order.id, items_data, request.user.username)

        return Response({"message": "Заказ оформлен", "order_id": order.id}, status=status.HTTP_201_CREATED)

    def get(self, request):
        # Показываем только оформленные заказы (не корзину)
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
# Берём URL с YAML-файлом, скачиваем и импортируем товары.
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

                # Создаём магазин или находим существующий
                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)

                # Добавляем категории
                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)

                # Удаляем старые товары этого магазина, чтобы не было дублей
                ProductInfo.objects.filter(shop_id=shop.id).delete()

                # Импортируем новые товары
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])
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


# Просто визуальный каталог, чтобы можно было глазами посмотреть товары.
def catalog_view(request):
    products = ProductInfo.objects.filter(quantity__gt=0, shop__state=True).prefetch_related('product_parameters')
    return render(request, 'catalog.html', {'products': products})


# Главная страница с навигацией по проекту.
def home_view(request):
    return render(request, 'home.html')