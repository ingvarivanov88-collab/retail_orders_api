from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ProductInfo, ProductParameter, Contact, OrderItem, Order

# Получаем кастомную модель User через get_user_model()
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        # По умолчанию пользователь неактивен (подтверждение по email)
        user.is_active = False
        user.save()
        return user


class ProductParameterSerializer(serializers.ModelSerializer):
    name = serializers.StringRelatedField(source='parameter')

    class Meta:
        model = ProductParameter
        fields = ['name', 'value']


class ProductInfoSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField(source='product.name')
    description = serializers.StringRelatedField(source='product.description')
    shop = serializers.StringRelatedField()
    parameters = ProductParameterSerializer(source='product_parameters', many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = ['id', 'product', 'description', 'shop', 'price', 'quantity', 'parameters']


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'first_name', 'last_name', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'phone']


class OrderItemSerializer(serializers.ModelSerializer):
    product_info = serializers.StringRelatedField()
    sum = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['product_info', 'quantity', 'sum']

    def get_sum(self, obj):
        return obj.product_info.price * obj.quantity


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(source='ordered_items', many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'dt', 'state', 'items', 'total']

    def get_total(self, obj):
        return sum(item.product_info.price * item.quantity for item in obj.ordered_items.all())