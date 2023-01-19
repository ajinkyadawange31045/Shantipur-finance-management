from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm,UsernameField
from django.contrib.auth.models import User
from django.utils.translation import gettext, gettext_lazy as _
from .models import Post

# class PostForm(forms.ModelForm):
#     class Meta:
#         model  = Post
#         fields = ['category','desc','amount_taken','amount_used','date','bill']
#         labels = {'desc':'Breif about purchased things'}
#         widgets = {
#             # 'title':forms.TextInput(attrs = {'class':'form-control'}),
#         'desc':forms.Textarea(attrs = {'class':'form-control','rows':4, 'cols':15}),
        
        
#         }


class PostForm(forms.ModelForm):
    class Meta:
        model  = Post
        fields = ['user','category','desc','amount_taken','amount_used','date','bill','remaining','status']
        labels = {'desc':'Breif about purchased things'}
        widgets = {
            # 'title':forms.TextInput(attrs = {'class':'form-control'}),
        'desc':forms.Textarea(attrs = {'class':'form-control','rows':4, 'cols':15}),
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(PostForm, self).__init__(*args, **kwargs)
        if not user.is_staff:
            self.fields.pop('user')
            self.fields.pop('remaining')
            self.fields.pop('status')



# class PostForm(forms.ModelForm):
#     class Meta:
#         model  = Post
#         fields = ['category','desc','amount_taken','amount_used','date','bill']
#         labels = {'desc':'Breif about purchased things'}
#         widgets = {
#             'desc':forms.Textarea(attrs = {'class':'form-control','rows':4, 'cols':15}),
#         }
#     def __init__(self, *args, **kwargs):
#         super(PostForm, self).__init__(*args, **kwargs)
#         if not self.user.is_superuser:
#             self.fields.pop('remaining')
#             self.fields.pop('status')

