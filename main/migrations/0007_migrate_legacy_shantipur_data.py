from django.db import migrations

def migrate_legacy_shantipur_data(apps, schema_editor):
    Center = apps.get_model('main', 'Center')
    CenterMembership = apps.get_model('main', 'CenterMembership')
    Post = apps.get_model('main', 'Post')
    User = apps.get_model('auth', 'User')

    # 1. Ensure default legacy center exists for Shantipur
    legacy_center, created = Center.objects.get_or_create(
        code='shantipur',
        defaults={
            'name': 'ISKCON Shantipur',
            'city': 'Shantipur',
            'state': 'West Bengal',
            'country': 'India',
            'status': 'APPROVED',
        }
    )

    # 2. Assign all existing posts without a center to the legacy Shantipur center
    unassigned_posts = Post.objects.filter(center__isnull=True)
    count = unassigned_posts.update(center=legacy_center)

    # 3. Assign existing users to the legacy Shantipur center
    for user in User.objects.all():
        role = 'MANAGER' if (user.is_staff or user.is_superuser) else 'VOLUNTEER'
        CenterMembership.objects.get_or_create(
            center=legacy_center,
            user=user,
            defaults={
                'role': role,
                'is_active': True,
            }
        )

def reverse_legacy_shantipur_data(apps, schema_editor):
    Center = apps.get_model('main', 'Center')
    CenterMembership = apps.get_model('main', 'CenterMembership')
    Post = apps.get_model('main', 'Post')

    try:
        legacy_center = Center.objects.get(code='shantipur')
        Post.objects.filter(center=legacy_center).update(center=None)
        CenterMembership.objects.filter(center=legacy_center).delete()
    except Center.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_add_center_and_membership_models'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_shantipur_data, reverse_legacy_shantipur_data),
    ]
