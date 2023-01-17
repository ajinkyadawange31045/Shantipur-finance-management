from django.http import HttpResponseRedirect
from django.shortcuts import render,HttpResponsePermanentRedirect
from django.contrib.auth.forms import UserCreationForm
from .forms import  PostForm
from django.contrib import messages
from django.contrib.auth import  authenticate,login,logout
from .models import Post
from django import forms
from django.contrib.auth.models import Group

#home
def home(request):
    posts = Post.objects.all().filter(status=True)
    # a = Post.objects.all().amount_taken()
    # print(a)
    # print(posts)
    # post = Post.objects.get(pk=1)
    
    
    
    context = {'posts':posts }
    return render(request,'home.html',context)

# #contact
# def contact(request):
#     return render(request,'contact.html')

#about
def about(request):
    return render(request,'about.html')

#dashboard
def dashboard(request):
    if request.user.is_authenticated:
        posts = Post.objects.all()
        user = request.user
        full_name = user.get_full_name()
        gps = user.groups.all()
        return render(request,'dashboard.html',{'posts':posts,'full_name':full_name,'gps':gps})
    else:
        return HttpResponseRedirect('/login/')

#add new post
def add_post(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = PostForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data['user']
                category = form.cleaned_data['category']
                # title = form.cleaned_data['title']
                amount_taken = form.cleaned_data['amount_taken']
                amount_used = form.cleaned_data['amount_used']
                desc = form.cleaned_data['desc']
                
                pst = Post(user=user,category=category,amount_taken=amount_taken,amount_used=amount_used, desc = desc)
                pst.user = request.user

                pst.save()
                return HttpResponseRedirect('/')

        else:
            form = PostForm()
        return render(request,'addpost.html',{'form':form})
    else:
        return HttpResponseRedirect('/login/')

#update new post
def update_post(request,id):
    if request.user.is_authenticated:
        if request.method == "POST":
            pi = Post.objects.get(pk=id)
            form = PostForm(request.POST, instance=pi)
            if form.is_valid():
                form.save()
                return HttpResponseRedirect('/dashboard/')
        else:
            pi = Post.objects.get(pk=id)
            form = PostForm(instance=pi)
        return render(request,'updatepost.html',{'form':form})
    else:
        return HttpResponseRedirect('/login/')

#delete new post
def delete_post(request,id):
    if request.user.is_authenticated:
        if request.method == "POST":
            pi = Post.objects.get(pk=id)
            pi.delete()
            return HttpResponseRedirect('/dashboard/')
    else:
        return HttpResponseRedirect('/login/')