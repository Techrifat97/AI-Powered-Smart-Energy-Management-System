from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .serializers import UserSerializer

User = get_user_model()


class UserListCreateView(generics.ListCreateAPIView):
    """
    List registered users or create a new user account.
    Requires an authenticated user session.
    """
    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]


class CurrentUserView(generics.RetrieveAPIView):
    """
    Return profile information for the currently authenticated user.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
