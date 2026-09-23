from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from drf_spectacular.utils import extend_schema
from rest_framework.throttling import AnonRateThrottle
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserMeSerializer,
    LogoutSerializer,
)


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'
    rate = '5/minute'


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Returns access and refresh tokens along with basic user details.
    Throttled to 5 requests per minute to prevent brute force.
    """
    throttle_classes = [LoginRateThrottle]
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the provided refresh token.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(
        request=LogoutSerializer,
        responses={200: {"description": "Successfully logged out."}, 400: {"description": "Invalid token."}}
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_200_OK
            )
        except TokenError:
            return Response(
                {"error": "Token is invalid or already expired."},
                status=status.HTTP_400_BAD_REQUEST
            )


class MeView(APIView):
    """
    GET /api/auth/me/
    Returns the authenticated user's ID, username, email, role,
    and (if role=SURVEYOR) their linked SurveyorProfile.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserMeSerializer

    @extend_schema(
        responses={200: UserMeSerializer}
    )
    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
