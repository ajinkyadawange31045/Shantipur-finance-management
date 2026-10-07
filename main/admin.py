from django.contrib import admin
from django.utils.timezone import now
from .models import Post, Center, CenterMembership, CenterInvitation

@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'code', 'city', 'status', 'submitted_by', 'approved_by', 'created_at']
    list_filter = ['status', 'city', 'state']
    search_fields = ['name', 'code', 'city']
    actions = ['approve_centers', 'reject_centers']

    def approve_centers(self, request, queryset):
        for center in queryset:
            center.status = 'APPROVED'
            center.approved_by = request.user
            center.approved_at = now()
            center.save()
            if center.submitted_by:
                CenterMembership.objects.get_or_create(
                    center=center,
                    user=center.submitted_by,
                    defaults={'role': 'MANAGER', 'is_active': True}
                )
    approve_centers.short_description = "Approve selected centers"

    def reject_centers(self, request, queryset):
        queryset.update(status='REJECTED')
    reject_centers.short_description = "Reject selected centers"


@admin.register(CenterMembership)
class CenterMembershipAdmin(admin.ModelAdmin):
    list_display = ['id', 'center', 'user', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'center']
    search_fields = ['user__username', 'center__name']


@admin.register(CenterInvitation)
class CenterInvitationAdmin(admin.ModelAdmin):
    list_display = ['id', 'email', 'center', 'role', 'status', 'invited_by', 'expires_at', 'accepted_by']
    list_filter = ['status', 'role', 'center']
    search_fields = ['email', 'center__name', 'token']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['id', 'center', 'date', 'user', 'category', 'desc', 'amount_taken', 'amount_used', 'to_be_returned', 'bill', 'remaining', 'settled_by', 'settled_at', 'status']
    list_filter = ['center', 'category', 'remaining', 'bill', 'status', 'date']
    search_fields = ['desc', 'user__username', 'category', 'center__name']

    def get_fields(self, request, obj=None):
        fields = ['center', 'user', 'category', 'desc', 'amount_taken', 'amount_used', 'date', 'bill']
        if request.user.is_superuser:
            fields.extend(['remaining', 'status'])
        return fields

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser and obj and obj.user != request.user:
            return ['center', 'user', 'category', 'desc', 'amount_taken', 'amount_used', 'date', 'bill']
        return []
