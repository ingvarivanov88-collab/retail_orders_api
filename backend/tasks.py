from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import yaml
from .models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter


@shared_task
def send_email(subject, message, recipient_list):
    """Универсальная задача для отправки email."""
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
        fail_silently=False,
    )


@shared_task
def do_import(file_path):
    """Фоновая задача для импорта товаров из YAML (поддерживает оба формата)."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    shop_name = data.get('shop')
    categories = data.get('categories', [])
    goods = data.get('goods', [])

    shop, _ = Shop.objects.get_or_create(name=shop_name)

    # Если в файле есть 'goods' (формат shop1.yaml)
    if goods:
        for item in goods:
            category_id = item.get('category')
            category = None
            if category_id:
                for cat in categories:
                    if cat.get('id') == category_id:
                        category, _ = Category.objects.get_or_create(id=category_id, name=cat.get('name'))
                        category.shops.add(shop)
                        break

            product, _ = Product.objects.get_or_create(name=item['name'], category=category)

            # Используем external_id, чтобы обновлять, а не создавать дубли
            product_info, _ = ProductInfo.objects.update_or_create(
                external_id=item['id'],
                product=product,
                shop=shop,
                defaults={
                    'model': item.get('model', ''),
                    'price': item['price'],
                    'price_rrc': item.get('price_rrc', item['price']),
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
    # Если в файле есть 'products' внутри категорий (формат shop_big.yaml)
    else:
        for cat_data in categories:
            cat_name = cat_data.get('name')
            category, _ = Category.objects.get_or_create(name=cat_name)
            category.shops.add(shop)

            products = cat_data.get('products', [])
            for prod_data in products:
                product, _ = Product.objects.get_or_create(name=prod_data['name'], category=category)

                # Если нет id — генерируем на основе названия (чтобы не было дублей)
                external_id = prod_data.get('id', 0)
                if not external_id:
                    external_id = abs(hash(prod_data['name'])) % 1000000

                product_info, _ = ProductInfo.objects.update_or_create(
                    external_id=external_id,
                    product=product,
                    shop=shop,
                    defaults={
                        'model': prod_data.get('model', ''),
                        'price': prod_data['price'],
                        'price_rrc': prod_data.get('price_rrc', prod_data['price']),
                        'quantity': prod_data.get('quantity', 0),
                    }
                )

                parameters = prod_data.get('parameters', [])
                for param in parameters:
                    parameter, _ = Parameter.objects.get_or_create(name=param['name'])
                    ProductParameter.objects.update_or_create(
                        product_info=product_info,
                        parameter=parameter,
                        defaults={'value': str(param['value'])}
                    )

    return f"Импорт завершён. Магазин: {shop_name}"


@shared_task
def send_order_confirmation_task(user_email, order_id, items):
    subject = f'Подтверждение заказа #{order_id}'
    message = f'Спасибо за ваш заказ #{order_id}!\n\n'
    message += 'Ваш заказ:\n'
    for item in items:
        message += f'- {item["product"]} (x{item["quantity"]})\n'
    send_email.delay(subject, message, [user_email])


@shared_task
def send_invoice_to_admin_task(order_id, items, username):
    subject = f'Новая накладная по заказу #{order_id}'
    message = f'Поступил новый заказ #{order_id} от {username}.\n\n'
    message += 'Состав заказа:\n'
    for item in items:
        message += f'- {item["product"]} (x{item["quantity"]}) — {item["price"]} руб.\n'
    send_email.delay(subject, message, ['admin@retail-orders-api.ru'])


@shared_task
def send_status_update_task(user_email, order_id, new_status):
    subject = f'Статус вашего заказа #{order_id} изменён'
    message = f'Статус вашего заказа #{order_id} был изменён на: {new_status}.\n'
    message += 'Спасибо, что выбрали нас!'
    send_email.delay(subject, message, [user_email])