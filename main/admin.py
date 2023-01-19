from django.contrib import admin
from .models import Post
# Register your models here.
# @admin.register(Post)
# class PostAdmin(admin.ModelAdmin):
#     # list_display=['id','date','user','category','desc','remaining']
#     list_display=['id','date','user','category','desc','remaining','amount_taken','amount_used','to_be_returned']
#     list_filter = ['category','remaining']


# admin.site.register(Post,PostAdmin)



class PostAdmin(admin.ModelAdmin):
    list_display=['id','date','user','category','desc','remaining']

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            form.base_fields.pop('remaining')
            form.base_fields.pop('status')
            if obj:
                if obj.user != request.user:
                    form.base_fields.pop('category')
                    form.base_fields.pop('desc')
                    form.base_fields.pop('amount_taken')
                    form.base_fields.pop('amount_used')
                    form.base_fields.pop('date')
                    form.base_fields.pop('bill')
        return form

admin.site.register(Post,PostAdmin)
