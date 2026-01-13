from django.urls import path

from .views import (
    UserRegistrationView, LogoutView, UserLoginView,
    ProfileView, ProfileEditView, StaffLoginRedirectView
)


app_name = 'accounts'

urlpatterns = [
    path(
        "login/", UserLoginView.as_view(),
        name="user_login"
    ),
    path(
        "logout/", LogoutView.as_view(),
        name="user_logout"
    ),
    path(
        "register/", UserRegistrationView.as_view(),
        name="user_registration"
    ),
    path(
        "profile/", ProfileView.as_view(),
        name='profile'
    ),
    path(
        "profile/edit/", ProfileEditView.as_view(),
        name='profile_edit'
    ),
    path(
        "staff-login/", StaffLoginRedirectView.as_view(),
        name='staff_login'
    ),
]
