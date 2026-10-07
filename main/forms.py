from django import forms
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.utils.text import slugify
from .models import Post, Center, CenterMembership, CenterInvitation, CENTER_ROLE_CHOICES


class PostForm(forms.ModelForm):
    center = forms.ModelChoiceField(
        queryset=Center.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )

    class Meta:
        model = Post
        fields = ['center', 'user', 'category', 'desc', 'amount_taken', 'amount_used', 'date', 'bill', 'remaining', 'status']
        labels = {
            'center': 'Center',
            'user': 'Devotee / Member',
            'desc': 'Brief description of purchased things',
            'amount_taken': 'Amount Taken (Rs.)',
            'amount_used': 'Amount Used (Rs.)',
            'remaining': 'Payment Settled / Returned',
            'bill': 'Bill Available',
            'status': 'Active Record'
        }
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'desc': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'cols': 15, 'placeholder': 'Item details...'}),
            'amount_taken': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'amount_used': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'bill': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'remaining': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None)
        self.active_center = kwargs.pop('center', None)
        super(PostForm, self).__init__(*args, **kwargs)

        target_center = self.instance.center if (self.instance and self.instance.pk and self.instance.center_id) else self.active_center

        # 1. Configure center queryset
        if self.request_user and self.request_user.is_superuser:
            self.fields['center'].queryset = Center.objects.filter(status='APPROVED').order_by('name')
        elif self.request_user:
            self.fields['center'].queryset = Center.objects.filter(
                memberships__user=self.request_user,
                memberships__is_active=True,
                status='APPROVED'
            ).distinct().order_by('name')
        else:
            self.fields['center'].queryset = Center.objects.none()

        # If editing an existing post, lock the center field
        if self.instance and self.instance.pk and self.instance.center_id:
            self.fields['center'].queryset = Center.objects.filter(id=self.instance.center_id)
            self.fields['center'].initial = self.instance.center
            self.fields['center'].disabled = True
        elif target_center:
            self.fields['center'].initial = target_center

        # 2. Determine user's role and capabilities in this center
        membership = None
        if self.request_user and target_center:
            membership = CenterMembership.objects.filter(
                user=self.request_user,
                center=target_center,
                is_active=True
            ).first()

        can_manage = bool(self.request_user and (self.request_user.is_superuser or (membership and membership.can_manage_members())))
        can_settle = bool(self.request_user and (self.request_user.is_superuser or (membership and membership.can_settle_expenses())))

        # User assignment control: Only Center Managers or Platform Admins can assign to another user
        if can_manage and target_center:
            self.fields['user'].queryset = User.objects.filter(
                center_memberships__center=target_center,
                center_memberships__is_active=True
            ).distinct().order_by('username')
            self.fields['user'].initial = self.instance.user if (self.instance and self.instance.pk) else self.request_user
        else:
            self.fields.pop('user', None)

        # Settlement authority: Volunteers cannot edit remaining/settlement flag
        if not can_settle:
            self.fields.pop('remaining', None)
            self.fields.pop('status', None)

    def clean_center(self):
        # On update, center CANNOT be changed
        if self.instance and self.instance.pk and self.instance.center_id:
            return self.instance.center

        center = self.cleaned_data.get('center') or self.active_center
        if not center:
            raise forms.ValidationError("An approved center must be selected.")

        if self.request_user and self.request_user.is_superuser:
            return center

        # Validate that requesting user is an active member of this center
        if not CenterMembership.objects.filter(user=self.request_user, center=center, is_active=True).exists():
            raise forms.ValidationError("You do not have membership permission to log expenses for this center.")

        return center

    def clean_user(self):
        # If user field was removed (for volunteers/members), always assign the requesting user
        if 'user' not in self.fields:
            if self.instance and self.instance.pk:
                return self.instance.user
            return self.request_user

        assigned_user = self.cleaned_data.get('user')
        if not assigned_user:
            return self.instance.user if (self.instance and self.instance.pk) else self.request_user

        target_center = self.cleaned_data.get('center') or self.active_center or (self.instance.center if self.instance and self.instance.pk else None)

        # Ensure the assigned user is actually a member of the center
        if target_center and not CenterMembership.objects.filter(user=assigned_user, center=target_center, is_active=True).exists():
            raise forms.ValidationError(f"User {assigned_user.username} is not an active member of {target_center.name}.")

        return assigned_user

    def clean_remaining(self):
        if 'remaining' not in self.fields:
            if self.instance and self.instance.pk:
                return self.instance.remaining
            return False
        return self.cleaned_data.get('remaining', False)

    def clean_status(self):
        if 'status' not in self.fields:
            if self.instance and self.instance.pk:
                return self.instance.status
            return True
        return self.cleaned_data.get('status', True)

    def save(self, commit=True):
        instance = super(PostForm, self).save(commit=False)
        if instance.remaining:
            if not instance.settled_at:
                instance.settled_by = self.request_user
                instance.settled_at = now()
        else:
            instance.settled_by = None
            instance.settled_at = None

        if commit:
            instance.save()
        return instance


class CenterApplicationForm(forms.ModelForm):
    code = forms.CharField(
        max_length=50,
        required=False,
        label='Center Slug / Code (optional)',
        help_text='Unique identifier (e.g. "iskcon-vrindavan"). Leave blank to automatically generate from the name.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. iskcon-vrindavan (optional)'})
    )

    class Meta:
        model = Center
        fields = ['name', 'code', 'address', 'city', 'state', 'country']
        labels = {
            'name': 'Center Name',
            'code': 'Center Code',
            'address': 'Address / Landmark',
            'city': 'City',
            'state': 'State / Province',
            'country': 'Country',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ISKCON Vrindavan'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Street address, landmark...'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Mathura'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Uttar Pradesh'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. India'}),
        }

    def __init__(self, *args, **kwargs):
        self.applicant = kwargs.pop('applicant', None)
        super(CenterApplicationForm, self).__init__(*args, **kwargs)
        self.fields['country'].required = False
        self.fields['country'].initial = 'India'

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Center name is required.")

        # Check for case-insensitive duplicate center name
        existing = Center.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        existing_center = existing.first()

        if existing_center:
            if existing_center.status == 'APPROVED':
                raise forms.ValidationError(f"A center named '{existing_center.name}' is already registered and active.")
            elif existing_center.status == 'PENDING':
                raise forms.ValidationError(f"An application for '{existing_center.name}' is already pending review.")
            else:
                raise forms.ValidationError(f"An application for '{existing_center.name}' was previously rejected. Please contact a platform admin.")

        return name

    def clean(self):
        cleaned_data = super(CenterApplicationForm, self).clean()
        name = cleaned_data.get('name')
        code = cleaned_data.get('code', '').strip() if cleaned_data.get('code') else ''

        # Auto-generate code from name if left blank
        if name and not code:
            code = slugify(name)[:50]
            if not code:
                code = f"center-{Center.objects.count() + 1}"
            cleaned_data['code'] = code

        if code:
            slugified = slugify(code)[:50]
            if not slugified:
                self.add_error('code', "Please enter a valid slug containing alphanumeric characters.")
            else:
                cleaned_data['code'] = slugified
                qs = Center.objects.filter(code=slugified)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    self.add_error('code', f"The center code '{slugified}' is already taken. Please choose a different code.")

        # Duplicate pending application check by the same applicant
        if self.applicant and name:
            pending = Center.objects.filter(submitted_by=self.applicant, status='PENDING', name__iexact=name)
            if self.instance and self.instance.pk:
                pending = pending.exclude(pk=self.instance.pk)
            if pending.exists():
                raise forms.ValidationError("You already have an active pending application for this center.")

        if not cleaned_data.get('country'):
            cleaned_data['country'] = 'India'

        return cleaned_data


class InviteVolunteerForm(forms.Form):
    email = forms.EmailField(
        label="Volunteer Email Address",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'volunteer@example.com'})
    )
    role = forms.ChoiceField(
        label="Initial Center Role",
        choices=CENTER_ROLE_CHOICES,
        initial='VOLUNTEER',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.center = kwargs.pop('center', None)
        super(InviteVolunteerForm, self).__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError("Please provide a valid email address.")
        if self.center:
            # Check if an active member already has this email
            if CenterMembership.objects.filter(center=self.center, user__email__iexact=email, is_active=True).exists():
                raise forms.ValidationError("A user with this email is already an active member of this center.")
            # Check if there is already an active pending invitation
            pending = CenterInvitation.objects.filter(center=self.center, email__iexact=email, status='PENDING')
            for inv in pending:
                if inv.is_valid():
                    raise forms.ValidationError(f"An active invitation has already been sent to {email}.")
        return email


class GrantMembershipForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput())
    role = forms.ChoiceField(
        label="Role",
        choices=CENTER_ROLE_CHOICES,
        initial='VOLUNTEER',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

