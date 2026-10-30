from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import (
    User, Shop, Category, Product,
    ProductInfo, Contact, OrderItem
)
from .tasks import do_import


class DiplomaAPITests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='test_buyer',
            email='buyer@example.com',
            password='TestPassword2026!',
            is_active=True
        )

        self.shop = Shop.objects.create(
            name='Тестовый магазин',
            state=True
        )

        category = Category.objects.create(
            name='Тестовая категория'
        )

        product = Product.objects.create(
            name='Тестовый товар',
            category=category
        )

        self.product_info = ProductInfo.objects.create(
            external_id=100,
            product=product,
            shop=self.shop,
            price=100,
            price_rrc=120,
            quantity=5
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_cart_cannot_exceed_stock(self):
        url = '/api/cart/'

        first = self.client.post(
            url,
            {
                'product_info_id': self.product_info.id,
                'quantity': 4
            },
            format='json'
        )

        second = self.client.post(
            url,
            {
                'product_info_id': self.product_info.id,
                'quantity': 4
            },
            format='json'
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)

        self.assertEqual(
            OrderItem.objects.get().quantity,
            4
        )

    def test_duplicate_email_rejected(self):
        response = self.client.post(
            '/api/register/',
            {
                'first_name': 'Иван',
                'last_name': 'Иванов',
                'email': 'buyer@example.com',
                'password': 'TestPassword2026!'
            },
            format='json'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

    def test_cart_contains_shop_and_total(self):
        self.client.post(
            '/api/cart/',
            {
                'product_info_id': self.product_info.id,
                'quantity': 2
            },
            format='json'
        )

        response = self.client.get('/api/cart/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 200)
        self.assertEqual(
            response.data['cart_items'][0]['shop'],
            'Тестовый магазин'
        )

    @patch('backend.views.send_invoice_to_admin_task.delay')
    @patch('backend.views.send_order_confirmation_task.delay')
    def test_order_reduces_stock(
        self, confirmation_mock, invoice_mock
    ):
        contact = Contact.objects.create(
            user=self.user,
            city='Москва',
            street='Ленина',
            house='10',
            phone='+79990000000'
        )

        self.client.post(
            '/api/cart/',
            {
                'product_info_id': self.product_info.id,
                'quantity': 3
            },
            format='json'
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                '/api/orders/',
                {'contact_id': contact.id},
                format='json'
            )

        self.product_info.refresh_from_db()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.product_info.quantity, 2)

        confirmation_mock.assert_called_once()
        invoice_mock.assert_called_once()

    def test_supplier_can_disable_orders(self):
        self.shop.user = self.user
        self.shop.save()

        response = self.client.patch(
            '/api/partner/state/',
            {'state': 'false'},
            format='json'
        )

        self.shop.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.shop.state)


class ImportTests(TestCase):

    def test_both_demo_files_import(self):
        do_import.run('shop_big.yaml')
        do_import.run('shop1.yaml')

        self.assertTrue(
            Shop.objects.filter(
                name='ТехноМир 2026'
            ).exists()
        )

        self.assertTrue(
            Shop.objects.filter(
                name='Магазин на диване'
            ).exists()
        )

        self.assertTrue(
            ProductInfo.objects.filter(
                shop__name='ТехноМир 2026'
            ).exists()
        )