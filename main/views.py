from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils.timezone import now
from django.urls import reverse
from django.core.mail import send_mail
from django.contrib.auth.models import User
from .forms import PostForm, CenterApplicationForm, InviteVolunteerForm, GrantMembershipForm
from .models import Post, Center, CenterMembership, CenterInvitation, CENTER_ROLE_CHOICES


def is_platform_admin(user):
    """Check if the user is a platform-wide administrator (superuser or staff)."""
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def get_user_centers(user):
    """Return all approved centers the user has active membership in (or all approved centers for platform superadmin)."""
    if not user.is_authenticated:
        return Center.objects.none()
    if user.is_superuser:
        return Center.objects.filter(status='APPROVED').order_by('name')
    return Center.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        status='APPROVED'
    ).distinct().order_by('name')


def get_active_center(request):
    """Determine the active center for the current request from session, query param, or user's first available membership."""
    if not request.user.is_authenticated:
        return None
    user_centers = get_user_centers(request.user)
    if not user_centers.exists():
        return None

    # 1. Query parameter override
    requested_center_id = request.GET.get('center')
    if requested_center_id:
        center = user_centers.filter(id=requested_center_id).first() or user_centers.filter(code=requested_center_id).first()
        if center:
            request.session['active_center_id'] = center.id
            return center

    # 2. Session preference
    session_center_id = request.session.get('active_center_id')
    if session_center_id:
        center = user_centers.filter(id=session_center_id).first()
        if center:
            return center

    # 3. Default to first available center
    center = user_centers.first()
    request.session['active_center_id'] = center.id
    return center


def get_user_membership(user, center):
    """Return the active CenterMembership for the user in the specified center, if one exists."""
    if not user.is_authenticated or not center:
        return None
    return CenterMembership.objects.filter(user=user, center=center, is_active=True).first()


def can_view_center(user, center):
    """Check if the user has permission to view center records."""
    if not user.is_authenticated or not center:
        return False
    if user.is_superuser:
        return True
    return CenterMembership.objects.filter(user=user, center=center, is_active=True).exists()


def can_manage_center_members(user, center):
    """
    Check if the user is authorized to manage memberships and invitations for a center:
    - Platform admin (is_superuser or is_staff)
    - Center Manager with active membership in this center
    """
    if not user.is_authenticated or not center:
        return False
    if user.is_superuser or user.is_staff:
        return True
    membership = get_user_membership(user, center)
    return bool(membership and membership.can_manage_members())


def can_add_expense(user, center):
    """Check if the user can log an expense in the center."""
    return can_view_center(user, center)


def can_edit_expense(user, post):
    """
    Check if the user can edit an expense:
    - Platform admin: can edit any expense.
    - Center Manager / In-Charge: can edit any expense in their center.
    - Volunteer: can ONLY edit their own expense, and ONLY if it is not settled yet.
    """
    if not user.is_authenticated or not post:
        return False
    if user.is_superuser:
        return True
    membership = get_user_membership(user, post.center)
    if not membership:
        return False
    if membership.role in ('MANAGER', 'IN_CHARGE'):
        return True
    if membership.role == 'VOLUNTEER' and post.user == user and not post.remaining:
        return True
    return False


def can_delete_expense(user, post):
    """
    Check if the user can delete an expense:
    - Platform admin: can delete any expense.
    - Center Manager: can delete any expense in their center.
    - Volunteer: can ONLY delete their own expense, and ONLY if it is not settled yet.
    """
    if not user.is_authenticated or not post:
        return False
    if user.is_superuser:
        return True
    membership = get_user_membership(user, post.center)
    if not membership:
        return False
    if membership.role == 'MANAGER':
        return True
    if membership.role == 'VOLUNTEER' and post.user == user and not post.remaining:
        return True
    return False


def can_settle_expense(user, post):
    """
    Check if the user is authorized to settle an expense:
    - Platform admin: can settle any expense.
    - Center In-Charge or Manager with active membership in the expense's center.
    """
    if not user.is_authenticated or not post or not post.center:
        return False
    if user.is_superuser:
        return True
    membership = get_user_membership(user, post.center)
    return bool(membership and membership.can_settle_expenses())


# Home: Center-scoped public listing for members
def home(request):
    if not request.user.is_authenticated:
        return render(request, 'home.html', {
            'posts': Post.objects.none(),
            'active_center': None,
            'user_centers': Center.objects.none()
        })

    user_centers = get_user_centers(request.user)
    active_center = get_active_center(request)

    if not active_center:
        return render(request, 'home.html', {
            'posts': Post.objects.none(),
            'active_center': None,
            'user_centers': user_centers
        })

    posts = Post.objects.filter(center=active_center, status=True).order_by('-id')
    return render(request, 'home.html', {
        'posts': posts,
        'active_center': active_center,
        'user_centers': user_centers
    })


# About / Guidelines
def about(request):
    return render(request, 'about.html')


# Dashboard: Center-scoped dashboard
def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    user_centers = get_user_centers(request.user)
    active_center = get_active_center(request)

    if not active_center:
        return render(request, 'dashboard.html', {
            'posts': Post.objects.none(),
            'active_center': None,
            'user_centers': user_centers,
            'full_name': request.user.get_full_name(),
            'can_manage': False,
            'can_settle': False,
            'settlement_filter': 'all',
            'total_count': 0,
            'unsettled_count': 0,
            'settled_count': 0,
        })

    if not can_view_center(request.user, active_center):
        raise PermissionDenied("You do not have permission to view expenses for this center.")

    membership = get_user_membership(request.user, active_center)
    can_manage = bool(request.user.is_superuser or (membership and membership.can_manage_members()))
    can_settle = bool(request.user.is_superuser or (membership and membership.can_settle_expenses()))

    all_posts = Post.objects.filter(center=active_center)
    total_count = all_posts.count()
    unsettled_count = all_posts.filter(remaining=False).count()
    settled_count = all_posts.filter(remaining=True).count()

    settlement_filter = request.GET.get('settlement', 'all')
    if settlement_filter == 'unsettled':
        posts = all_posts.filter(remaining=False)
    elif settlement_filter == 'settled':
        posts = all_posts.filter(remaining=True)
    else:
        posts = all_posts

    posts = posts.select_related('user', 'settled_by').order_by('remaining', '-id')

    return render(request, 'dashboard.html', {
        'posts': posts,
        'active_center': active_center,
        'user_centers': user_centers,
        'full_name': request.user.get_full_name(),
        'membership': membership,
        'can_manage': can_manage,
        'can_settle': can_settle,
        'settlement_filter': settlement_filter,
        'total_count': total_count,
        'unsettled_count': unsettled_count,
        'settled_count': settled_count,
    })



# Add a new expense
def add_post(request):
    if not request.user.is_authenticated:
        return redirect('login')

    user_centers = get_user_centers(request.user)
    active_center = get_active_center(request)

    if not active_center or not can_add_expense(request.user, active_center):
        raise PermissionDenied("You do not have membership permission to add expenses in this center.")

    if request.method == 'POST':
        form = PostForm(request.POST, user=request.user, center=active_center)
        if form.is_valid():
            post = form.save(commit=False)
            target_center = form.cleaned_data.get('center') or active_center

            # View-level validation: prevent unauthorized center assignment
            if not can_add_expense(request.user, target_center):
                raise PermissionDenied("Unauthorized center.")
            post.center = target_center

            # View-level validation: enforce user assignment rules
            post.user = form.cleaned_data.get('user') or request.user

            if not post.date:
                post.date = now()

            post.save()
            messages.success(request, 'Entry added successfully!')
            return redirect('dashboard')
    else:
        form = PostForm(user=request.user, center=active_center)

    return render(request, 'addpost.html', {
        'form': form,
        'active_center': active_center,
        'user_centers': user_centers
    })


# Update an existing entry
def update_post(request, id):
    if not request.user.is_authenticated:
        return redirect('login')

    post = get_object_or_404(Post, pk=id)

    # View-level permission check
    if not can_edit_expense(request.user, post):
        raise PermissionDenied("You do not have permission to edit this entry.")

    if request.method == "POST":
        form = PostForm(request.POST, instance=post, user=request.user, center=post.center)
        if form.is_valid():
            saved_post = form.save(commit=False)
            # Enforce that post center is immutable across edits
            saved_post.center = post.center

            if not saved_post.date:
                saved_post.date = now()

            saved_post.save()
            messages.success(request, 'Entry updated successfully!')
            return redirect('dashboard')
    else:
        form = PostForm(instance=post, user=request.user, center=post.center)

    return render(request, 'updatepost.html', {
        'form': form,
        'post': post,
        'active_center': post.center
    })


# Delete an existing entry
def delete_post(request, id):
    if not request.user.is_authenticated:
        return redirect('login')

    post = get_object_or_404(Post, pk=id)

    # View-level permission check
    if not can_delete_expense(request.user, post):
        raise PermissionDenied("You do not have permission to delete this entry.")

    if request.method == "POST":
        post.delete()
        messages.success(request, 'Entry deleted successfully!')
    return redirect('dashboard')


# Settle an expense entry
def settle_expense(request, id):
    """
    CSRF-protected server-side action for Center In-Charge / Managers
    to settle an expense with audit trail (settled_by, settled_at)
    and prevention of accidental repeat settlements.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method != 'POST':
        return redirect('dashboard')

    post = get_object_or_404(Post, pk=id)

    # Permission check: must have settle rights for this center
    if not can_settle_expense(request.user, post):
        raise PermissionDenied("You do not have permission to settle expenses in this center.")

    # Prevent accidental repeat settlement
    if post.remaining:
        settler_name = post.settled_by.username if post.settled_by else "an administrator"
        settle_time = post.settled_at.strftime('%d %b %Y %H:%M') if post.settled_at else "earlier"
        messages.warning(
            request,
            f"Expense #{post.id} was already settled by {settler_name} on {settle_time}."
        )
        next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
        return redirect(next_url)

    # Settle with audit fields
    post.remaining = True
    post.settled_by = request.user
    post.settled_at = now()
    post.save()

    messages.success(
        request,
        f"Expense #{post.id} for {post.user.username} (Rs. {post.amount_used}) settled successfully."
    )
    next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
    return redirect(next_url)


def bulk_settle_expenses(request):
    """
    CSRF-protected batch settlement action for multiple expenses at once.
    Only settles expenses belonging to centers where the user has settle authority.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method != 'POST':
        return redirect('dashboard')

    post_ids = request.POST.getlist('post_ids')
    if not post_ids:
        messages.warning(request, "No expenses were selected for settlement.")
        next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
        return redirect(next_url)

    settled_count = 0
    skipped_count = 0

    with transaction.atomic():
        for post_id in post_ids:
            try:
                post = Post.objects.select_for_update().get(pk=post_id)
            except (Post.DoesNotExist, ValueError):
                continue

            if not can_settle_expense(request.user, post):
                raise PermissionDenied(f"You do not have permission to settle Expense #{post.id} in {post.center.name}.")

            if post.remaining:
                skipped_count += 1
                continue

            post.remaining = True
            post.settled_by = request.user
            post.settled_at = now()
            post.save()
            settled_count += 1

    if settled_count > 0:
        messages.success(request, f"Successfully settled {settled_count} expense record(s).")
    if skipped_count > 0:
        messages.info(request, f"{skipped_count} record(s) were already settled and skipped.")

    next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
    return redirect(next_url)




# ==========================================
# Center Application Workflow Views
# ==========================================

def apply_center(request):
    """Allow an authenticated user to submit an application to register a new center."""
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method == 'POST':
        form = CenterApplicationForm(request.POST, applicant=request.user)
        if form.is_valid():
            try:
                center = form.save(commit=False)
                center.status = 'PENDING'
                center.submitted_by = request.user
                center.save()
                messages.success(
                    request,
                    f"Application for '{center.name}' submitted successfully! It is now pending review by a platform admin."
                )
                return redirect('apply_center')
            except IntegrityError:
                form.add_error(None, "A center with this name or unique code already exists.")
    else:
        form = CenterApplicationForm(applicant=request.user)

    my_applications = Center.objects.filter(submitted_by=request.user).order_by('-created_at')

    return render(request, 'apply_center.html', {
        'form': form,
        'my_applications': my_applications,
        'is_admin': is_platform_admin(request.user),
    })


def my_center_applications(request):
    """View user's submitted center applications."""
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect('apply_center')


def center_applications_list(request):
    """Platform admins only: review pending and past center applications."""
    if not request.user.is_authenticated:
        return redirect('login')

    if not is_platform_admin(request.user):
        raise PermissionDenied("Only platform administrators can review center applications.")

    pending_applications = Center.objects.filter(status='PENDING').order_by('-created_at')
    processed_applications = Center.objects.exclude(status='PENDING').order_by('-updated_at')[:30]

    return render(request, 'center_applications.html', {
        'pending_applications': pending_applications,
        'processed_applications': processed_applications,
    })


def approve_center_application(request, center_id):
    """Platform admins only: approve a pending center application and grant applicant Manager role."""
    if not request.user.is_authenticated:
        return redirect('login')

    if not is_platform_admin(request.user):
        raise PermissionDenied("Only platform administrators can approve center applications.")

    if request.method != 'POST':
        return redirect('center_applications_list')

    center = get_object_or_404(Center, pk=center_id)

    if center.status != 'PENDING':
        messages.warning(request, f"Center '{center.name}' is already {center.get_status_display().lower()}.")
        return redirect('center_applications_list')

    center.status = 'APPROVED'
    center.approved_by = request.user
    center.approved_at = now()
    center.save()

    # Grant the applicant the initial Center Manager role
    if center.submitted_by:
        membership, created = CenterMembership.objects.get_or_create(
            center=center,
            user=center.submitted_by,
            defaults={'role': 'MANAGER', 'is_active': True}
        )
        if not created:
            membership.role = 'MANAGER'
            membership.is_active = True
            membership.save()
        messages.success(
            request,
            f"Center '{center.name}' approved! {center.submitted_by.username} has been granted the Center Manager role."
        )
    else:
        messages.success(request, f"Center '{center.name}' approved!")

    return redirect('center_applications_list')


def reject_center_application(request, center_id):
    """Platform admins only: reject a pending center application."""
    if not request.user.is_authenticated:
        return redirect('login')

    if not is_platform_admin(request.user):
        raise PermissionDenied("Only platform administrators can reject center applications.")

    if request.method != 'POST':
        return redirect('center_applications_list')

    center = get_object_or_404(Center, pk=center_id)

    if center.status != 'PENDING':
        messages.warning(request, f"Center '{center.name}' is already {center.get_status_display().lower()}.")
        return redirect('center_applications_list')

    center.status = 'REJECTED'
    center.approved_by = request.user
    center.approved_at = now()
    center.save()

    messages.info(request, f"Application for '{center.name}' was rejected.")
    return redirect('center_applications_list')


# ==========================================
# Center Membership & Invitation Management
# ==========================================

def center_members(request, center_id):
    """View and manage members and invitations for a specific center (Manager / Platform Admin only)."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to manage members for this center.")

    # Search for an existing user account by exact username without exposing unnecessary info
    search_query = request.GET.get('search_username', '').strip()
    searched_user = None
    searched_membership = None
    if search_query:
        target = User.objects.filter(username__iexact=search_query).first()
        if target:
            # Strictly expose minimal account info (no email, passwords, superuser status)
            searched_user = {
                'id': target.id,
                'username': target.username,
                'display_name': target.get_full_name() or target.username,
            }
            searched_membership = CenterMembership.objects.filter(center=center, user=target).first()
        else:
            messages.info(request, f"No user account found with username '{search_query}'.")

    memberships = CenterMembership.objects.filter(center=center).select_related('user').order_by('role', 'user__username')
    invitations = CenterInvitation.objects.filter(center=center).select_related('invited_by', 'accepted_by').order_by('-created_at')

    invite_form = InviteVolunteerForm(center=center)
    grant_form = GrantMembershipForm()

    return render(request, 'center_members.html', {
        'center': center,
        'memberships': memberships,
        'invitations': invitations,
        'invite_form': invite_form,
        'grant_form': grant_form,
        'searched_user': searched_user,
        'searched_membership': searched_membership,
        'search_query': search_query,
        'role_choices': CENTER_ROLE_CHOICES,
    })


def invite_volunteer(request, center_id):
    """Authorized managers invite a volunteer by email with an expiring token."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to invite members to this center.")

    if request.method == 'POST':
        form = InviteVolunteerForm(request.POST, center=center)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            invitation = CenterInvitation.objects.create(
                center=center,
                email=email,
                role=role,
                invited_by=request.user,
            )

            # Attempt to send notification email (fail-safe for console/smtp)
            try:
                invite_url = request.build_absolute_uri(reverse('view_invitation', args=[invitation.token]))
                send_mail(
                    subject=f"Invitation to join {center.name}",
                    message=(
                        f"Hare Krishna!\n\n"
                        f"You have been invited to join {center.name} as a {invitation.get_role_display()}.\n\n"
                        f"Please click the link below to accept your invitation (valid for 7 days):\n"
                        f"{invite_url}\n\n"
                        f"Thank you!"
                    ),
                    from_email='noreply@iskcon.org',
                    recipient_list=[email],
                    fail_silently=True,
                )
            except Exception:
                pass

            messages.success(
                request,
                f"Invitation sent to '{email}' as {invitation.get_role_display()}! (Token: {invitation.token})"
            )
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)

    return redirect('center_members', center_id=center.id)


def grant_user_membership(request, center_id):
    """Grant or update center membership to an existing user account found by username search."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to grant membership in this center.")

    if request.method == 'POST':
        form = GrantMembershipForm(request.POST)
        if form.is_valid():
            user_id = form.cleaned_data['user_id']
            role = form.cleaned_data['role']
            target_user = get_object_or_404(User, pk=user_id)

            membership, created = CenterMembership.objects.get_or_create(
                center=center,
                user=target_user,
                defaults={'role': role, 'is_active': True}
            )
            if not created:
                membership.role = role
                membership.is_active = True
                membership.save()

            messages.success(
                request,
                f"Granted {membership.get_role_display()} membership to {target_user.username} in {center.name}."
            )
        else:
            messages.error(request, "Invalid membership form submission.")

    return redirect('center_members', center_id=center.id)


def revoke_user_membership(request, center_id, membership_id):
    """Revoke (deactivate) a user's membership in the center."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to revoke memberships in this center.")

    if request.method != 'POST':
        return redirect('center_members', center_id=center.id)

    membership = get_object_or_404(CenterMembership, pk=membership_id, center=center)

    # Protect against manager revoking themselves
    if membership.user == request.user and not request.user.is_superuser:
        messages.error(request, "You cannot revoke your own membership.")
        return redirect('center_members', center_id=center.id)

    membership.is_active = False
    membership.save()
    messages.success(request, f"Revoked {membership.user.username}'s membership in {center.name}.")

    return redirect('center_members', center_id=center.id)


def reactivate_user_membership(request, center_id, membership_id):
    """Reactivate a previously revoked user membership."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to reactivate memberships in this center.")

    if request.method != 'POST':
        return redirect('center_members', center_id=center.id)

    membership = get_object_or_404(CenterMembership, pk=membership_id, center=center)
    membership.is_active = True
    membership.save()
    messages.success(request, f"Reactivated {membership.user.username}'s membership in {center.name}.")

    return redirect('center_members', center_id=center.id)


def change_member_role(request, center_id, membership_id):
    """Change role of a member in the center."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to change roles in this center.")

    if request.method == 'POST':
        membership = get_object_or_404(CenterMembership, pk=membership_id, center=center)
        new_role = request.POST.get('role')
        valid_roles = [r[0] for r in CENTER_ROLE_CHOICES]
        if new_role in valid_roles:
            membership.role = new_role
            membership.save()
            messages.success(request, f"Updated {membership.user.username}'s role to {membership.get_role_display()}.")
        else:
            messages.error(request, "Invalid role specified.")

    return redirect('center_members', center_id=center.id)


def revoke_invitation(request, center_id, invitation_id):
    """Revoke a pending email invitation."""
    if not request.user.is_authenticated:
        return redirect('login')

    center = get_object_or_404(Center, pk=center_id)

    if not can_manage_center_members(request.user, center):
        raise PermissionDenied("You do not have permission to revoke invitations for this center.")

    if request.method != 'POST':
        return redirect('center_members', center_id=center.id)

    invitation = get_object_or_404(CenterInvitation, pk=invitation_id, center=center)
    invitation.status = 'REVOKED'
    invitation.save()
    messages.info(request, f"Revoked invitation for '{invitation.email}'.")

    return redirect('center_members', center_id=center.id)


def view_invitation(request, token):
    """Public view for recipients of an invitation link to accept or sign up."""
    invitation = CenterInvitation.objects.filter(token=token).first()
    if not invitation:
        messages.error(request, "This invitation link is invalid or has expired.")
        return render(request, 'accept_invitation.html', {'invitation': None})

    if invitation.status == 'REVOKED':
        messages.error(request, "This invitation has been revoked by the center manager.")
        return render(request, 'accept_invitation.html', {'invitation': None})

    if invitation.status == 'ACCEPTED':
        messages.info(request, "This invitation has already been accepted.")
        return render(request, 'accept_invitation.html', {'invitation': invitation, 'already_accepted': True})

    if invitation.is_expired:
        invitation.status = 'EXPIRED'
        invitation.save()
        messages.warning(request, "This invitation has expired. Please ask the center manager for a new invitation.")
        return render(request, 'accept_invitation.html', {'invitation': invitation, 'expired': True})

    # If authenticated, allow accepting the invitation
    email_matches = False
    if request.user.is_authenticated:
        user_email = (request.user.email or '').strip().lower()
        invite_email = (invitation.email or '').strip().lower()
        email_matches = bool(user_email and invite_email and user_email == invite_email)

        if request.method == 'POST':
            if not email_matches:
                raise PermissionDenied(
                    f"This invitation was sent to '{invitation.email}', but you are signed in as '{request.user.username}' ({request.user.email or 'no email address'}). Please sign in with the invited email address."
                )
            # Proof of invitation: single-use token consumed
            success = invitation.accept(request.user)
            if success:
                request.session['active_center_id'] = invitation.center.id
                messages.success(
                    request,
                    f"Welcome to {invitation.center.name}! You are now a {invitation.get_role_display()}."
                )
                return redirect('dashboard')
            else:
                messages.error(request, "Could not accept invitation.")
                return redirect('dashboard')

    return render(request, 'accept_invitation.html', {
        'invitation': invitation,
        'user_is_authenticated': request.user.is_authenticated,
        'email_matches': email_matches,
    })