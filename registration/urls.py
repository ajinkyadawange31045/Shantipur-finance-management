
from django.urls import path,include
from . import views
urlpatterns = [
    path('signup_ard_31045/',views.user_signup,name='signup'),    
    path('login/',views.user_login,name='login'),   
    path('logout/',views.user_logout,name='logout'),
]