from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm,UsernameField
from django.contrib.auth.models import User
from django.utils.translation import gettext, gettext_lazy as _
from .models import Post

class PostForm(forms.ModelForm):
    class Meta:
        model  = Post
        fields = ['category','desc','amount_taken','amount_used','date','bill']
        labels = {'desc':'Breif about purchased things'}
        widgets = {
            # 'title':forms.TextInput(attrs = {'class':'form-control'}),
        'desc':forms.Textarea(attrs = {'class':'form-control','rows':4, 'cols':15}),
        
        
        }