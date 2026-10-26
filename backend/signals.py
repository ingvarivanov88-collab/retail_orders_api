from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import User, ConfirmEmailToken


# Сигнал срабатывает после создания нового пользователя
@receiver(post_save, sender=User)
def create_confirm_token(sender, instance, created, **kwargs):
    if created:
        # Создаём токен для подтверждения email
        token = ConfirmEmailToken.objects.create(user=instance)
        # Отправляем письмо с токеном
        send_mail(
            'Подтверждение регистрации',
            f'Здравствуйте, {instance.username}!\n\n'
            f'Спасибо за регистрацию. Ваш токен подтверждения: {token.key}\n'
            f'Отправьте его на /api/register/confirm/ для активации аккаунта.',
            settings.DEFAULT_FROM_EMAIL,
            [instance.email],
            fail_silently=False,
        )