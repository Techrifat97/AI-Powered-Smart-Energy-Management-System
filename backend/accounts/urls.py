from django.urls import path
from .views import UserListCreateView, CurrentUserView

urlpatterns = [
    path('users/', UserListCreateView.as_view(), name='user-list-create'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
]

