from django.contrib import admin
from .models import Post
# Register your models here.
# @admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_diaplay=['id','category','desc']
admin.site.register(Post,PostAdmin)