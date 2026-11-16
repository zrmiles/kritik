from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    public_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "public_name")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("username", "display_name", "password", "password_confirm")

    def validate(self, attrs):
        password = attrs.get("password")
        if password != attrs.pop("password_confirm", None):
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        candidate = User(username=attrs.get("username", ""), display_name=attrs.get("display_name", ""))
        validate_password(password, user=candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
