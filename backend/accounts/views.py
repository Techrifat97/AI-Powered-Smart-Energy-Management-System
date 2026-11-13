from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.response import Response
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


class UserDetailView(generics.RetrieveDestroyAPIView):
    """
    Retrieve or delete a user account.
    Authenticated users can remove accounts, but cannot delete the primary admin
    or their own active account.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.username.lower() == 'admin' or instance.is_superuser:
            return Response(
                {"detail": "The primary admin account cannot be removed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if instance.id == request.user.id:
            return Response(
                {"detail": "You cannot delete your own active account."},
                status=status.HTTP_400_BAD_REQUEST
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(generics.RetrieveAPIView):
    """
    Return profile information for the currently authenticated user.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
