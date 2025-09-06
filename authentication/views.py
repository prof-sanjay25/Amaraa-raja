from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User
from .serializers import CustomTokenSerializer

class CustomTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        return token

class CustomTokenView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer

class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer

import random
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=400)

    try:
        user = User.objects.get(email=email)
        otp = random.randint(100000, 999999)

        user.reset_otp = otp
        user.reset_otp_created_at = timezone.now()
        user.save()

        # Send OTP via email
        send_mail(
            'Password Reset OTP',
            f'Your OTP for password reset is {otp}. It will expire in 10 minutes.',
            'noreply@yourdomain.com',
            [email],
            fail_silently=False,
        )
        return Response({'message': 'OTP sent to email.'})
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=404)


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    email = request.data.get('email')
    otp = request.data.get('otp')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not all([email, otp, new_password, confirm_password]):
        return Response({'error': 'Missing fields.'}, status=400)

    if new_password != confirm_password:
        return Response({'error': 'Passwords do not match.'}, status=400)

    try:
        user = User.objects.get(email=email)

        if not user.is_reset_otp_valid(otp):
            return Response({'error': 'Invalid or expired OTP.'}, status=400)

        try:
            User.validate_password_strength(new_password)
        except ValidationError as e:
            return Response({'error': str(e)}, status=400)

        user.set_password(new_password)
        user.reset_otp = None
        user.reset_otp_created_at = None
        user.save()

        return Response({'message': 'Password reset successful.'})
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=404)
