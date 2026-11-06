from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .serializers import LoginSerializer, UserSerializer
from .throttles import LoginAccountThrottle, LoginIpThrottle


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Prime the csrftoken cookie so the frontend can echo it back.

    Called once before the first unsafe request. get_token() is what actually
    sets the cookie; returning the value too spares the client a cookie read.
    """
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginIpThrottle, LoginAccountThrottle])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        request,
        username=serializer.validated_data["username"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        # Deliberately vague: distinguishing "no such user" from "wrong
        # password" tells an attacker which usernames exist.
        return Response(
            {"detail": "Incorrect username or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user.is_active:
        return Response(
            {"detail": "This account is disabled."},
            status=status.HTTP_403_FORBIDDEN,
        )

    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)
