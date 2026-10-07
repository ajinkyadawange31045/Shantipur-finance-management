from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .forms import SignUpForm, LoginForm

# Logout
def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')

# Login
def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            uname = form.cleaned_data['username']
            upass = form.cleaned_data['password']
            user = authenticate(username=uname, password=upass)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

# Signup
def user_signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    invitation_token = request.GET.get('invitation') or request.POST.get('invitation_token')
    invitation = None
    if invitation_token:
        from main.models import CenterInvitation
        inv = CenterInvitation.objects.filter(token=invitation_token).first()
        if inv and inv.is_valid():
            invitation = inv
        else:
            messages.warning(request, 'The invitation link is invalid or has expired.')

    if request.method == "POST":
        form = SignUpForm(request.POST, invitation=invitation)
        if form.is_valid():
            user = form.save()
            if invitation and invitation.is_valid():
                invitation.accept(user)
                messages.success(
                    request,
                    f"Account created and membership granted in {invitation.center.name}! Please log in."
                )
            else:
                messages.success(request, 'Account created successfully! Please log in.')
            return redirect('login')
    else:
        form = SignUpForm(invitation=invitation)

    return render(request, 'signup.html', {
        'form': form,
        'invitation': invitation
    })
