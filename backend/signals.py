from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django_rest_passwordreset.signals import reset_password_token_created
from .models import User, ConfirmEmailToken


# Сигнал: создаём токен и отправляем письмо при регистрации
@receiver(post_save, sender=User)
def create_confirm_token(sender, instance, created, **kwargs):
    if created:
        token = ConfirmEmailToken.objects.create(user=instance)
        send_mail(
            'Подтверждение регистрации',
            f'Здравствуйте, {instance.username}!\n\n'
            f'Спасибо за регистрацию. Ваш токен подтверждения: {token.key}\n'
            f'Отправьте его на /api/register/confirm/ для активации аккаунта.',
            settings.DEFAULT_FROM_EMAIL,
            [instance.email],
            fail_silently=False,
        )


# Сигнал: отправляем письмо при запросе сброса пароля
@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    send_mail(
        'Сброс пароля',
        f'Здравствуйте, {reset_password_token.user.username}!\n\n'
        f'Ваш токен для сброса пароля: {reset_password_token.key}\n'
        f'Отправьте его на /api/password_reset/confirm/ для смены пароля.',
        settings.DEFAULT_FROM_EMAIL,
        [reset_password_token.user.email],
        fail_silently=False,
    )