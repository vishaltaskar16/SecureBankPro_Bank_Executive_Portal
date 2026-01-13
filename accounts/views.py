from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import HttpResponseRedirect, render, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, RedirectView
from django.views import View

from .forms import (
    UserRegistrationForm,
    UserAddressForm,
    UserProfileForm,
    UserBankAccountForm,
)


User = get_user_model()


class UserRegistrationView(TemplateView):
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/user_registration.html'

    def dispatch(self, request, *args, **kwargs):
        if self.request.user.is_authenticated:
            return HttpResponseRedirect(
                reverse_lazy('transactions:transaction_report')
            )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        registration_form = UserRegistrationForm(self.request.POST)
        address_form = UserAddressForm(self.request.POST)

        if registration_form.is_valid() and address_form.is_valid():
            user = registration_form.save()
            address = address_form.save(commit=False)
            address.user = user
            address.save()

            login(self.request, user)
            messages.success(
                self.request,
                (
                    f'Thank You For Creating A Bank Account. '
                    f'Your Account Number is {user.account.account_no}. '
                )
            )
            return HttpResponseRedirect(
                reverse_lazy('transactions:deposit_money')
            )

        return self.render_to_response(
            self.get_context_data(
                registration_form=registration_form,
                address_form=address_form
            )
        )

    def get_context_data(self, **kwargs):
        if 'registration_form' not in kwargs:
            kwargs['registration_form'] = UserRegistrationForm()
        if 'address_form' not in kwargs:
            kwargs['address_form'] = UserAddressForm()

        return super().get_context_data(**kwargs)


class UserLoginView(LoginView):
    template_name='accounts/user_login.html'
    redirect_authenticated_user = False

    def form_valid(self, form):
        # Log the user in first
        response = super().form_valid(form)
        user = self.request.user
        # If the user is staff (admin), redirect to the Django admin interface
        if user.is_active and (user.is_staff or user.is_superuser):
            return HttpResponseRedirect(reverse_lazy('admin:index'))
        return response


from django.views.generic import RedirectView


class StaffLoginRedirectView(RedirectView):
    """A convenience URL for staff to jump to the Django admin login."""
    permanent = False
    pattern_name = 'admin:login'


class LogoutView(RedirectView):
    pattern_name = 'home'

    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            logout(self.request)
        return super().get_redirect_url(*args, **kwargs)


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user'] = self.request.user
        ctx['account'] = getattr(self.request.user, 'account', None)
        ctx['address'] = getattr(self.request.user, 'address', None)
        return ctx


class ProfileEditView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        user = request.user
        account = getattr(user, 'account', None)
        address = getattr(user, 'address', None)

        user_form = UserProfileForm(instance=user)
        address_form = UserAddressForm(instance=address)
        account_form = UserBankAccountForm(instance=account)

        return render(request, 'accounts/profile_edit.html', {
            'user_form': user_form,
            'address_form': address_form,
            'account_form': account_form,
        })

    def post(self, request, *args, **kwargs):
        user = request.user
        account = getattr(user, 'account', None)
        address = getattr(user, 'address', None)

        user_form = UserProfileForm(request.POST, instance=user)
        address_form = UserAddressForm(request.POST, instance=address)
        account_form = UserBankAccountForm(request.POST, instance=account)

        if user_form.is_valid() and address_form.is_valid() and account_form.is_valid():
            user_form.save()
            address_form.save()
            # Account form will not allow changing account_no; save allowed fields
            account_instance = account_form.save(commit=False)
            account_instance.user = user
            account_instance.save()

            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')

        return render(request, 'accounts/profile_edit.html', {
            'user_form': user_form,
            'address_form': address_form,
            'account_form': account_form,
        })