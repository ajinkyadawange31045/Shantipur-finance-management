from django.contrib import admin
from django.urls import path
from django.urls import include
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('',views.home),
    path('about/',views.about,name='about'),
    # path('contact/',views.contact,name='contact'),
    # path('contact/',views.contact,name='contact'),
    path('dashboard/',views.dashboard,name='dashboard'),
    # path('signup/',views.user_signup,name='signup'),
    # path('login/',views.user_login,name='login'),
    # path('logout/',views.user_logout,name='logout'),
    path('addpost/',views.add_post,name='addpost'),
    path('updatepost/<int:id>/',views.update_post, name='updatepost'),
    path('delete/<int:id>/',views.delete_post,name='deletepost'),
    path('settle/<int:id>/', views.settle_expense, name='settle_expense'),
    path('settle/bulk/', views.bulk_settle_expenses, name='bulk_settle_expenses'),

    # Center application workflow routes
    path('centers/apply/', views.apply_center, name='apply_center'),
    path('centers/my-applications/', views.my_center_applications, name='my_center_applications'),
    path('centers/applications/', views.center_applications_list, name='center_applications_list'),
    path('centers/applications/<int:center_id>/approve/', views.approve_center_application, name='approve_center_application'),
    path('centers/applications/<int:center_id>/reject/', views.reject_center_application, name='reject_center_application'),

    # Center membership & invitation routes
    path('centers/<int:center_id>/members/', views.center_members, name='center_members'),
    path('centers/<int:center_id>/members/invite/', views.invite_volunteer, name='invite_volunteer'),
    path('centers/<int:center_id>/members/grant/', views.grant_user_membership, name='grant_user_membership'),
    path('centers/<int:center_id>/members/<int:membership_id>/revoke/', views.revoke_user_membership, name='revoke_user_membership'),
    path('centers/<int:center_id>/members/<int:membership_id>/reactivate/', views.reactivate_user_membership, name='reactivate_user_membership'),
    path('centers/<int:center_id>/members/<int:membership_id>/role/', views.change_member_role, name='change_member_role'),
    path('centers/<int:center_id>/invitations/<int:invitation_id>/revoke/', views.revoke_invitation, name='revoke_invitation'),
    path('invitations/<str:token>/', views.view_invitation, name='view_invitation'),
]
