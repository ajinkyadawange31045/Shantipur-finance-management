from .models import Center
from .views import get_user_centers, get_active_center, get_user_membership, is_platform_admin


def center_context(request):
    """
    Context processor providing active center, user centers,
    and role capabilities globally across all templates.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'nav_user_centers': Center.objects.none(),
            'nav_active_center': None,
            'nav_membership': None,
            'nav_can_manage': False,
            'nav_can_settle': False,
            'is_platform_admin': False,
        }

    user_centers = get_user_centers(request.user)
    active_center = get_active_center(request)
    membership = get_user_membership(request.user, active_center) if active_center else None
    can_manage = bool(request.user.is_superuser or (membership and membership.can_manage_members()))
    can_settle = bool(request.user.is_superuser or (membership and membership.can_settle_expenses()))

    return {
        'nav_user_centers': user_centers,
        'nav_active_center': active_center,
        'nav_membership': membership,
        'nav_can_manage': can_manage,
        'nav_can_settle': can_settle,
        'is_platform_admin': is_platform_admin(request.user),
    }
