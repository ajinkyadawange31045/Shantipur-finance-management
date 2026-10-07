import secrets
from datetime import timedelta
from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User

CENTER_STATUS_CHOICES = [
    ('PENDING', 'Pending Approval'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
]

CENTER_ROLE_CHOICES = [
    ('MANAGER', 'Center Manager'),
    ('IN_CHARGE', 'Center In-Charge'),
    ('VOLUNTEER', 'Volunteer / Member'),
]

INVITATION_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('ACCEPTED', 'Accepted'),
    ('EXPIRED', 'Expired'),
    ('REVOKED', 'Revoked'),
]


def default_invitation_expiry():
    return now() + timedelta(days=7)


def generate_invitation_token():
    return secrets.token_urlsafe(32)

SELECT_CATEGORY_CHOICES = [
    ("Kitchen Food", "Kitchen Food"),
    ("Petrol", "Petrol"),
    ("item purchasing", "item purchasing"),
    ("Necessities", "Necessities"),
    ("Other", "Other")
]


class Center(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=50, unique=True, help_text="Short unique identifier / slug for the center")
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, default='India')
    status = models.CharField(max_length=20, choices=CENTER_STATUS_CHOICES, default='PENDING')
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='submitted_centers')
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_centers')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_approved(self):
        return self.status == 'APPROVED'


class CenterMembership(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='center_memberships')
    role = models.CharField(max_length=20, choices=CENTER_ROLE_CHOICES, default='VOLUNTEER')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=now)

    class Meta:
        unique_together = ('center', 'user')
        ordering = ['center', 'role', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.center.name} ({self.get_role_display()})"

    @property
    def is_manager(self):
        return self.role == 'MANAGER'

    @property
    def is_in_charge(self):
        return self.role == 'IN_CHARGE'

    @property
    def is_volunteer(self):
        return self.role == 'VOLUNTEER'

    def can_settle_expenses(self):
        return self.is_active and self.role in ('MANAGER', 'IN_CHARGE')

    def can_manage_members(self):
        return self.is_active and self.role == 'MANAGER'


class CenterInvitation(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=CENTER_ROLE_CHOICES, default='VOLUNTEER')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_center_invitations')
    token = models.CharField(max_length=64, unique=True, default=generate_invitation_token)
    status = models.CharField(max_length=20, choices=INVITATION_STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(default=now)
    expires_at = models.DateTimeField(default=default_invitation_expiry)
    accepted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='accepted_center_invitations')
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invitation for {self.email} to {self.center.name} ({self.get_status_display()})"

    @property
    def is_expired(self):
        if self.status == 'EXPIRED':
            return True
        if self.status == 'PENDING' and self.expires_at <= now():
            return True
        return False

    def is_valid(self):
        return self.status == 'PENDING' and self.expires_at > now()

    def accept(self, user):
        if not self.is_valid():
            return False
        if not user or not user.is_authenticated:
            return False
        # Prevent an unrelated account with a different email from accepting
        user_email = (user.email or '').strip().lower()
        invite_email = (self.email or '').strip().lower()
        if user_email and invite_email and user_email != invite_email:
            return False
        membership, created = CenterMembership.objects.get_or_create(
            center=self.center,
            user=user,
            defaults={'role': self.role, 'is_active': True}
        )
        if not created:
            membership.role = self.role
            membership.is_active = True
            membership.save()
        self.status = 'ACCEPTED'
        self.accepted_by = user
        self.accepted_at = now()
        self.save()
        return True


class Post(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name='posts')
    user = models.ForeignKey(User, default=1, on_delete=models.CASCADE)
    category = models.CharField(max_length=200, choices=SELECT_CATEGORY_CHOICES, default='Food', null=True)
    amount_taken = models.BigIntegerField()
    amount_used = models.BigIntegerField()
    date = models.DateTimeField(default=now, null=True)
    desc = models.TextField(null=True)
    bill = models.BooleanField(default=False)
    remaining = models.BooleanField(default=False)
    status = models.BooleanField(default=True)
    settled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='settled_expenses')
    settled_at = models.DateTimeField(null=True, blank=True)

    @property
    def to_be_returned(self):
        return self.amount_taken - self.amount_used

    def settle(self, user):
        """Settle this expense record with audit trail, preventing accidental repeat settlement."""
        if self.remaining:
            return False, "This expense is already settled."
        self.remaining = True
        self.settled_by = user
        self.settled_at = now()
        self.save()
        return True, "Expense settled successfully."

    def __str__(self):
        center_name = self.center.name if self.center else "No Center"
        return f"[{center_name}] {self.user.username} - {self.category} ({self.amount_used} Rs.)"