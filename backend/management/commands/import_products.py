import yaml
from django.core.management.base import BaseCommand
from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter


class Command(BaseCommand):
    help = 'Импорт товаров из YAML-файла (поддерживает оба формата)'

    def add_arguments(self, parser):
        parser.add_argument('yaml_file', type=str, help='Путь к YAML-файлу')

    def handle(self, *args, **options):
        file_path = options['yaml_file']
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        shop_name = data.get('shop')
        categories = data.get('categories', [])
        goods = data.get('goods', [])

        shop, _ = Shop.objects.get_or_create(name=shop_name)
        self.stdout.write(f"Магазин: {shop.name}")

        # Если формат shop1.yaml (с goods)
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
                self.stdout.write(f"  Товар: {product.name}")
        # Если формат shop_big.yaml (с products внутри категорий)
        else:
            for cat_data in categories:
                cat_name = cat_data.get('name')
                category, _ = Category.objects.get_or_create(name=cat_name)
                category.shops.add(shop)
                self.stdout.write(f"  Категория: {category.name}")

                products = cat_data.get('products', [])
                for prod_data in products:
                    product, _ = Product.objects.get_or_create(name=prod_data['name'], category=category)

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
                    self.stdout.write(f"    Товар: {product.name}")

        self.stdout.write(self.style.SUCCESS('Импорт завершён!'))