from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import User

class CustomTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["role"] = user.role
        token["circle"] = getattr(user, "circle", None)  # ✅ added
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Inject extra fields into login response (not just in JWT claims)
        data.update({
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.role,
            "circle": getattr(self.user, "circle", None),
        })
        return data
