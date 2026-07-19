from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    is_manager = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_manager",
        )
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    # write_only: never echoed back in a response or error payload.
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
