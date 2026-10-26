from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ProductInfo, ProductParameter, Contact, OrderItem, Order

# Получаем кастомную модель User через get_user_model()
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User  # <-- Используем класс модели, а не строку
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user


class ProductParameterSerializer(serializers.ModelSerializer):
    name = serializers.StringRelatedField(source='parameter')

    class Meta:
        model = ProductParameter
        fields = ['name', 'value']


class ProductInfoSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    shop = serializers.StringRelatedField()
    parameters = ProductParameterSerializer(source='product_parameters', many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = ['id', 'product', 'shop', 'price', 'quantity', 'parameters']


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'first_name', 'last_name', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'phone']


class OrderItemSerializer(serializers.ModelSerializer):
    product_info = serializers.StringRelatedField()

    class Meta:
        model = OrderItem
        fields = ['product_info', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(source='ordered_items', many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'dt', 'state', 'items']