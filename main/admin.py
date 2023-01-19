from django.contrib import admin
from .models import Post
# Register your models here.
# @admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    # list_display=['id','date','user','category','desc','remaining']
    list_display=['id','date','user','category','desc','remaining','amount_taken','amount_used','to_be_returned']
    list_filter = ['category','remaining']


admin.site.register(Post,PostAdmin)