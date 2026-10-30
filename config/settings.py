"""
Настройки Django для проекта config.
"""

from pathlib import Path
import os

# Путь к корню проекта (используется для статики, шаблонов и т.д.)
BASE_DIR = Path(__file__).resolve().parent.parent


# Секретный ключ. В продакшене должен храниться в переменных окружения.
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-8#8b9u6&5#8v9k5#2v6y0v#8b9u6&5#8v9k5#2v6y0v#8b9u6&5')

# Режим отладки. В продакшене обязательно выключать.
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# Разрешаем запросы с любых хостов (для локальной разработки).
ALLOWED_HOSTS = ['*']


# Подключённые приложения
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',           # Django REST Framework
    'rest_framework.authtoken', # Токены для авторизации
    'django_rest_passwordreset',# Восстановление пароля
    'backend',                  # Наше приложение
]

# Middleware — промежуточные обработчики запросов
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Главный файл с маршрутами
ROOT_URLCONF = 'config.urls'

# Настройки шаблонов (HTML-страницы)
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Папка с нашими шаблонами
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Точка входа для WSGI (используется в продакшене)
WSGI_APPLICATION = 'config.wsgi.application'


# Подключение к базе данных PostgreSQL.
# Данные берутся из переменных окружения (которые передаёт Docker Compose).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'retail_orders_db'),
        'USER': os.getenv('POSTGRES_USER', 'retail_user'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'retail_pass'),
        'HOST': os.getenv('DB_HOST', 'db'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}


# Валидаторы паролей (стандартные от Django)
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Язык и часовой пояс
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Настройки статики (CSS, JS, картинки)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Тип первичного ключа по умолчанию
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- КАСТОМНАЯ МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ ---
# Указываем Django, что нужно использовать нашу модель User (с полем type),
# а не стандартную. Без этой настройки поле type не будет работать.
AUTH_USER_MODEL = 'backend.User'

# Настройки Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    # --- ДОБАВИЛ ПАГИНАЦИЮ: теперь API отдаёт список товаров постранично ---
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}

# Куда перенаправлять после входа/выхода
LOGIN_REDIRECT_URL = '/api/products/'
LOGOUT_REDIRECT_URL = '/api/products/'

# --- НАСТРОЙКА EMAIL ---
# Письма выводятся в консоль (для тестов). В продакшене заменить на SMTP.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@retail-orders-api.ru'

# Адрес администратора, на который уходят накладные по заказам.
# Можно переопределить через переменную окружения ADMIN_ORDER_EMAIL.
ADMIN_ORDER_EMAIL = os.getenv('ADMIN_ORDER_EMAIL', 'admin@example.com')

# --- НАСТРОЙКА CELERY ---
# Redis используется как брокер сообщений и хранилище результатов.
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'