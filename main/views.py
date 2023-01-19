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
    posts = Post.objects.all().filter(status=True).order_by('-id')
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
        posts = Post.objects.all().order_by('remaining')
        user = request.user
        full_name = user.get_full_name()
        gps = user.groups.all()
        return render(request,'dashboard.html',{'posts':posts,'full_name':full_name,'gps':gps})
    else:
        return HttpResponseRedirect('/login/')

from django.shortcuts import render, HttpResponseRedirect
from .forms import PostForm
from .models import Post

def add_post(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = PostForm(request.POST,user=request.user)
            if form.is_valid():
                post = form.save(commit=False)
                post.user = request.user
                post.save()
                return HttpResponseRedirect('/dashboard/')
        else:
            form = PostForm(user=request.user)
        return render(request,'addpost.html',{'form':form})
    else:
        return HttpResponseRedirect('/login/')

from django.shortcuts import render, get_object_or_404, HttpResponseRedirect
from .forms import PostForm
from .models import Post

def update_post(request,id):
    post = Post.objects.get(pk=id)
    if request.user.is_authenticated:
        if request.user == post.user or request.user.is_staff:
            if request.method == "POST":
                form = PostForm(request.POST, instance=post,user=request.user)
                if form.is_valid():
                    form.save()
                    return HttpResponseRedirect('/dashboard/')
            else:
                form = PostForm(instance=post,user=request.user)
            return render(request,'updatepost.html',{'form':form})
        else:
            return HttpResponseRedirect('/dashboard/')
    else:
        return HttpResponseRedirect('/login/')

# def update_post(request, id):
#     post = get_object_or_404(Post, id=id)
#     # Check if the current user is the creator of the post or if they are an admin user
#     if request.user != post.user and not request.user.is_superuser:
#         return HttpResponseRedirect('/dashboard/') # or return a 403 error
#     if request.method == "POST":
#         form = PostForm(request.POST, instance=post,user=request.user)
#         if form.is_valid():
#             form.save()
#             return HttpResponseRedirect('/dashboard/')
#     else:
#         form = PostForm(instance=post,user=request.user)
#     return render(request, 'updatepost.html', {'form': form})



#delete new post
def delete_post(request,id):
    if request.user.is_authenticated:
        if request.method == "POST":
            pi = Post.objects.get(pk=id)
            pi.delete()
            return HttpResponseRedirect('/dashboard/')
    else:
        return HttpResponseRedirect('/login/')