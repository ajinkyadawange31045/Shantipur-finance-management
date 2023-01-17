from django.shortcuts import render
from .forms import SignUpForm,LoginForm

from django.http import HttpResponseRedirect
from django.shortcuts import render,HttpResponsePermanentRedirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth import  authenticate,login,logout
# from .models import Post
from django import forms
from django.contrib.auth.models import Group

#home
# Create your views here.

#logout
def user_logout(request):
    logout(request)
    return HttpResponsePermanentRedirect('/')

#login
def user_login(request):
    if not request.user.is_authenticated:
        if request.method == "POST":
            form = LoginForm(request =request,data=request.POST)
            if form.is_valid():
                uname = form.cleaned_data['username']
                upass = form.cleaned_data['password']
                user = authenticate(username=uname,password = upass)
                if user is not None:
                    login(request,user)
                    messages.success(request,'Logged in Successfully')
                    return HttpResponsePermanentRedirect('/')
        else:
            form = LoginForm()
        return render(request,'login.html',{'form':form})
    else:
        return HttpResponseRedirect('/')


#signup
def user_signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            messages.success(request,'Congratulations!! successfullly signed in')
            user = form.save()
            # group = Group.objects.get(name ='Author')
            # user.groups.add(group)
    else:
        form = SignUpForm()
    return render(request,'signup.html',{'form':form})
