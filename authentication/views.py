from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenSerializer  # ✅ use the one from serializers.py


class CustomTokenView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer


class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer
