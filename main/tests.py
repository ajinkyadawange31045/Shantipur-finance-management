from datetime import timedelta
from django.utils.timezone import now
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
from django.db.utils import IntegrityError
from .models import Post, Center, CenterMembership, CenterInvitation


class CenterAndMembershipModelTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username='platform_admin', password='Password@123', email='admin@iskcon.org'
        )
        self.devotee1 = User.objects.create_user(
            username='radha_raman', password='Password@123', first_name='Radha Raman'
        )
        self.devotee2 = User.objects.create_user(
            username='madhava', password='Password@123', first_name='Madhava'
        )

    def test_create_center_and_approval_workflow(self):
        # 1. User submits a center application
        center = Center.objects.create(
            name='ISKCON Mayapur',
            code='mayapur',
            city='Mayapur',
            state='West Bengal',
            country='India',
            submitted_by=self.devotee1
        )
        self.assertEqual(center.status, 'PENDING')
        self.assertFalse(center.is_approved)

        # 2. Platform admin approves center
        center.status = 'APPROVED'
        center.approved_by = self.superadmin
        center.save()
        self.assertTrue(center.is_approved)
        self.assertEqual(center.approved_by, self.superadmin)

    def test_center_unique_constraints(self):
        Center.objects.create(name='ISKCON Vrindavan', code='vrindavan', status='APPROVED')
        # Duplicate name
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Center.objects.create(name='ISKCON Vrindavan', code='vrindavan_2', status='APPROVED')
        # Duplicate code
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Center.objects.create(name='ISKCON Krishna Balaram', code='vrindavan', status='APPROVED')

    def test_membership_roles_and_helpers(self):
        center = Center.objects.create(name='ISKCON Mumbai', code='mumbai', status='APPROVED')

        manager_membership = CenterMembership.objects.create(
            center=center, user=self.devotee1, role='MANAGER'
        )
        in_charge_membership = CenterMembership.objects.create(
            center=center, user=self.devotee2, role='IN_CHARGE'
        )

        volunteer_user = User.objects.create_user(username='volunteer1', password='Password@123')
        volunteer_membership = CenterMembership.objects.create(
            center=center, user=volunteer_user, role='VOLUNTEER'
        )

        # Check Manager capabilities
        self.assertTrue(manager_membership.is_manager)
        self.assertTrue(manager_membership.can_manage_members())
        self.assertTrue(manager_membership.can_settle_expenses())

        # Check Center-in-charge capabilities
        self.assertTrue(in_charge_membership.is_in_charge)
        self.assertFalse(in_charge_membership.can_manage_members())
        self.assertTrue(in_charge_membership.can_settle_expenses())

        # Check Volunteer capabilities
        self.assertTrue(volunteer_membership.is_volunteer)
        self.assertFalse(volunteer_membership.can_manage_members())
        self.assertFalse(volunteer_membership.can_settle_expenses())

    def test_user_can_belong_to_multiple_centers(self):
        center_delhi = Center.objects.create(name='ISKCON Delhi', code='delhi', status='APPROVED')
        center_kolkata = Center.objects.create(name='ISKCON Kolkata', code='kolkata', status='APPROVED')

        # devotee1 is MANAGER in Delhi and VOLUNTEER in Kolkata
        mem_delhi = CenterMembership.objects.create(
            center=center_delhi, user=self.devotee1, role='MANAGER'
        )
        mem_kolkata = CenterMembership.objects.create(
            center=center_kolkata, user=self.devotee1, role='VOLUNTEER'
        )

        user_centers = Center.objects.filter(memberships__user=self.devotee1)
        self.assertEqual(user_centers.count(), 2)
        self.assertIn(center_delhi, user_centers)
        self.assertIn(center_kolkata, user_centers)

        # Ensure unique_together prevents duplicate membership in the same center
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                CenterMembership.objects.create(
                    center=center_delhi, user=self.devotee1, role='VOLUNTEER'
                )

    def test_platform_admin_distinct_from_center_roles(self):
        # Platform admin has superuser authority without requiring a specific center role
        self.assertTrue(self.superadmin.is_superuser)
        self.assertEqual(self.superadmin.center_memberships.count(), 0)

        # Center manager is NOT a platform superuser or staff
        center = Center.objects.create(name='ISKCON Pune', code='pune', status='APPROVED')
        CenterMembership.objects.create(center=center, user=self.devotee1, role='MANAGER')

        self.assertFalse(self.devotee1.is_superuser)
        self.assertFalse(self.devotee1.is_staff)

    def test_post_center_association_and_scoping(self):
        center_a = Center.objects.create(name='Center A', code='center-a', status='APPROVED')
        center_b = Center.objects.create(name='Center B', code='center-b', status='APPROVED')

        post_a = Post.objects.create(
            center=center_a,
            user=self.devotee1,
            amount_taken=1000,
            amount_used=800,
            desc='Center A flowers'
        )
        post_b = Post.objects.create(
            center=center_b,
            user=self.devotee2,
            amount_taken=500,
            amount_used=500,
            desc='Center B fruits'
        )

        self.assertEqual(Post.objects.filter(center=center_a).count(), 1)
        self.assertEqual(Post.objects.filter(center=center_a).first(), post_a)
        self.assertEqual(Post.objects.filter(center=center_b).count(), 1)
        self.assertEqual(Post.objects.filter(center=center_b).first(), post_b)


class FinanceManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='testuser1', password='Password@123', first_name='John')
        self.user2 = User.objects.create_user(username='testuser2', password='Password@123', first_name='Jane')
        self.staff_user = User.objects.create_user(username='staffuser', password='Password@123', is_staff=True)

        self.center, _ = Center.objects.get_or_create(
            code='shantipur',
            defaults={'name': 'ISKCON Shantipur', 'status': 'APPROVED'}
        )
        CenterMembership.objects.get_or_create(center=self.center, user=self.user1, defaults={'role': 'MANAGER'})
        CenterMembership.objects.get_or_create(center=self.center, user=self.user2, defaults={'role': 'VOLUNTEER'})

        self.post1 = Post.objects.create(
            center=self.center,
            user=self.user1,
            category='Kitchen Food',
            amount_taken=1000,
            amount_used=750,
            desc='Vegetables and groceries',
            bill=True,
            remaining=False,
            status=True
        )

    def test_home_page(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ISKCON Shantipur')
        self.assertContains(response, 'Vegetables and groceries')

    def test_home_page_unauthenticated_does_not_leak_records(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Vegetables and groceries')

    def test_about_page(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Important Guidelines & Rules')

    def test_to_be_returned_calculation(self):
        self.assertEqual(self.post1.to_be_returned, 250)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_dashboard_authenticated(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')

    def test_add_post(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.post(reverse('addpost'), {
            'center': self.center.id,
            'category': 'Petrol',
            'amount_taken': 500,
            'amount_used': 500,
            'desc': 'Fuel for delivery',
            'bill': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Post.objects.filter(desc='Fuel for delivery').exists())

    def test_update_post_owner(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post1.id]), {
            'center': self.center.id,
            'category': 'Kitchen Food',
            'amount_taken': 1200,
            'amount_used': 800,
            'desc': 'Updated groceries',
            'bill': True
        })
        self.assertEqual(response.status_code, 302)
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.amount_taken, 1200)
        self.assertEqual(self.post1.desc, 'Updated groceries')

    def test_update_post_forbidden_for_other_user(self):
        self.client.login(username='testuser2', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post1.id]), {
            'center': self.center.id,
            'category': 'Petrol',
            'amount_taken': 9999,
            'amount_used': 9999,
            'desc': 'Hacked',
        })
        self.assertEqual(response.status_code, 403)
        self.post1.refresh_from_db()
        self.assertNotEqual(self.post1.desc, 'Hacked')

    def test_delete_post_owner(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post1.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(id=self.post1.id).exists())

    def test_delete_post_forbidden_for_other_user(self):
        self.client.login(username='testuser2', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post1.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.post1.id).exists())

    def test_delete_post_404(self):
        self.client.login(username='testuser1', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[999999]))
        self.assertEqual(response.status_code, 404)


class CenterAwareExpenseAccessTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Centers
        self.center_a = Center.objects.create(name='ISKCON Mayapur', code='mayapur', status='APPROVED')
        self.center_b = Center.objects.create(name='ISKCON Vrindavan', code='vrindavan', status='APPROVED')

        # Users
        self.manager_a = User.objects.create_user(username='manager_a', password='Password@123', first_name='Manager A')
        self.in_charge_a = User.objects.create_user(username='incharge_a', password='Password@123', first_name='In Charge A')
        self.volunteer_a1 = User.objects.create_user(username='volunteer_a1', password='Password@123', first_name='Vol A1')
        self.volunteer_a2 = User.objects.create_user(username='volunteer_a2', password='Password@123', first_name='Vol A2')

        self.volunteer_b = User.objects.create_user(username='volunteer_b', password='Password@123', first_name='Vol B')

        # Memberships
        CenterMembership.objects.create(center=self.center_a, user=self.manager_a, role='MANAGER')
        CenterMembership.objects.create(center=self.center_a, user=self.in_charge_a, role='IN_CHARGE')
        CenterMembership.objects.create(center=self.center_a, user=self.volunteer_a1, role='VOLUNTEER')
        CenterMembership.objects.create(center=self.center_a, user=self.volunteer_a2, role='VOLUNTEER')

        CenterMembership.objects.create(center=self.center_b, user=self.volunteer_b, role='VOLUNTEER')

        # Expenses
        self.post_a1 = Post.objects.create(
            center=self.center_a,
            user=self.volunteer_a1,
            category='Kitchen Food',
            amount_taken=1000,
            amount_used=800,
            desc='Mayapur bhoga vegetables',
            bill=True,
            remaining=False,
            status=True
        )

        self.post_b1 = Post.objects.create(
            center=self.center_b,
            user=self.volunteer_b,
            category='Petrol',
            amount_taken=500,
            amount_used=500,
            desc='Vrindavan parikrama fuel',
            bill=True,
            remaining=False,
            status=True
        )

    def test_cross_center_isolation_on_home_and_dashboard(self):
        # Volunteer A1 logs in
        self.client.login(username='volunteer_a1', password='Password@123')

        # Home page shows only Center A records
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mayapur bhoga vegetables')
        self.assertNotContains(response, 'Vrindavan parikrama fuel')

        # Dashboard shows only Center A records
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mayapur bhoga vegetables')
        self.assertNotContains(response, 'Vrindavan parikrama fuel')

    def test_dashboard_access_to_unauthorized_center_forbidden(self):
        self.client.login(username='volunteer_a1', password='Password@123')
        # Tries to access Center B via ?center=
        response = self.client.get(f"{reverse('dashboard')}?center={self.center_b.id}")
        # Volunteer A1 does not belong to Center B, so active center remains Center A
        self.assertNotContains(response, 'Vrindavan parikrama fuel')

    def test_create_expense_in_unauthorized_center_blocked(self):
        self.client.login(username='volunteer_a1', password='Password@123')
        # Tries to post an expense into Center B
        response = self.client.post(reverse('addpost'), {
            'center': self.center_b.id,
            'category': 'Petrol',
            'amount_taken': 300,
            'amount_used': 300,
            'desc': 'Illegitimate expense in Center B',
        })
        self.assertFalse(Post.objects.filter(desc='Illegitimate expense in Center B').exists())

    def test_volunteer_cannot_assign_expense_to_another_user(self):
        self.client.login(username='volunteer_a1', password='Password@123')
        response = self.client.post(reverse('addpost'), {
            'center': self.center_a.id,
            'user': self.volunteer_a2.id,
            'category': 'Other',
            'amount_taken': 400,
            'amount_used': 400,
            'desc': 'Volunteer trying to assign to another',
        })
        self.assertEqual(response.status_code, 302)
        created_post = Post.objects.get(desc='Volunteer trying to assign to another')
        # Field was ignored and forced to the authenticated user
        self.assertEqual(created_post.user, self.volunteer_a1)

    def test_manager_cannot_assign_expense_to_non_center_member(self):
        self.client.login(username='manager_a', password='Password@123')
        # Volunteer B is NOT a member of Center A
        response = self.client.post(reverse('addpost'), {
            'center': self.center_a.id,
            'user': self.volunteer_b.id,
            'category': 'Other',
            'amount_taken': 500,
            'amount_used': 500,
            'desc': 'Assigning to outsider',
        })
        # Should fail form validation
        self.assertFalse(Post.objects.filter(desc='Assigning to outsider').exists())

    def test_edit_cross_center_expense_forbidden(self):
        # Volunteer B belongs to Center B, tries to edit Post in Center A
        self.client.login(username='volunteer_b', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'amount_taken': 9999,
            'amount_used': 9999,
            'desc': 'Tampered across centers',
        })
        self.assertEqual(response.status_code, 403)
        self.post_a1.refresh_from_db()
        self.assertNotEqual(self.post_a1.desc, 'Tampered across centers')

    def test_edit_other_user_expense_forbidden_for_volunteer(self):
        # Volunteer A2 tries to edit Volunteer A1's post in same Center A
        self.client.login(username='volunteer_a2', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'amount_taken': 2000,
            'amount_used': 2000,
            'desc': 'Tampered by peer volunteer',
        })
        self.assertEqual(response.status_code, 403)
        self.post_a1.refresh_from_db()
        self.assertNotEqual(self.post_a1.desc, 'Tampered by peer volunteer')

    def test_edit_settled_expense_forbidden_for_volunteer(self):
        # Settle post A1
        self.post_a1.remaining = True
        self.post_a1.save()

        # Creator volunteer_a1 tries to edit after settlement
        self.client.login(username='volunteer_a1', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'amount_taken': 1500,
            'amount_used': 1500,
            'desc': 'Editing after settled',
        })
        self.assertEqual(response.status_code, 403)

    def test_manager_and_incharge_can_edit_any_expense_in_center(self):
        # Manager A can edit post A1
        self.client.login(username='manager_a', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'category': 'Kitchen Food',
            'amount_taken': 1000,
            'amount_used': 850,
            'desc': 'Adjusted by manager',
        })
        self.assertEqual(response.status_code, 302)
        self.post_a1.refresh_from_db()
        self.assertEqual(self.post_a1.desc, 'Adjusted by manager')

        # In-charge A can also edit and settle post A1
        self.client.login(username='incharge_a', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'category': 'Kitchen Food',
            'amount_taken': 1000,
            'amount_used': 850,
            'desc': 'Settled by in-charge',
            'remaining': True
        })
        self.assertEqual(response.status_code, 302)
        self.post_a1.refresh_from_db()
        self.assertTrue(self.post_a1.remaining)

    def test_center_remains_immutable_on_update(self):
        self.client.login(username='manager_a', password='Password@123')
        # Manager tries to switch post_a1 to center_b
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'center': self.center_b.id,
            'category': 'Kitchen Food',
            'amount_taken': 1000,
            'amount_used': 800,
            'desc': 'Attempting center change',
        })
        self.assertEqual(response.status_code, 302)
        self.post_a1.refresh_from_db()
        # Center MUST remain center_a
        self.assertEqual(self.post_a1.center, self.center_a)

    def test_volunteer_cannot_tamper_settlement_on_update(self):
        self.client.login(username='volunteer_a1', password='Password@123')
        # Post A1 is not settled
        self.assertFalse(self.post_a1.remaining)

        # Volunteer submits remaining=True
        response = self.client.post(reverse('updatepost', args=[self.post_a1.id]), {
            'category': 'Kitchen Food',
            'amount_taken': 1000,
            'amount_used': 800,
            'desc': 'Volunteer trying to settle own expense',
            'remaining': True
        })
        self.assertEqual(response.status_code, 302)
        self.post_a1.refresh_from_db()
        # Settlement flag MUST remain False
        self.assertFalse(self.post_a1.remaining)

    def test_delete_cross_center_forbidden(self):
        self.client.login(username='volunteer_b', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post_a1.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.post_a1.id).exists())

    def test_delete_other_user_expense_forbidden_for_volunteer(self):
        self.client.login(username='volunteer_a2', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post_a1.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.post_a1.id).exists())

    def test_delete_settled_expense_forbidden_for_volunteer(self):
        self.post_a1.remaining = True
        self.post_a1.save()

        self.client.login(username='volunteer_a1', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post_a1.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.post_a1.id).exists())

    def test_manager_can_delete_expense_in_center(self):
        self.client.login(username='manager_a', password='Password@123')
        response = self.client.post(reverse('deletepost', args=[self.post_a1.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(id=self.post_a1.id).exists())


class CenterApplicationWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin_user', password='Password@123', email='admin@iskcon.org'
        )
        self.applicant = User.objects.create_user(
            username='applicant_bhakta', password='Password@123', email='bhakta@iskcon.org'
        )
        self.other_user = User.objects.create_user(
            username='regular_devotee', password='Password@123', email='devotee@iskcon.org'
        )

        # Ensure legacy Shantipur center exists (from migration 0007)
        self.shantipur_center, _ = Center.objects.get_or_create(
            code='shantipur',
            defaults={
                'name': 'ISKCON Shantipur',
                'status': 'APPROVED',
                'country': 'India',
            }
        )

        # Create an existing Center Manager for Shantipur (non-platform admin)
        self.center_manager = User.objects.create_user(
            username='shantipur_manager', password='Password@123', email='manager@shantipur.org'
        )
        CenterMembership.objects.create(
            center=self.shantipur_center,
            user=self.center_manager,
            role='MANAGER',
            is_active=True
        )

    def test_unauthenticated_user_redirected_to_login_on_apply(self):
        response = self.client.get(reverse('apply_center'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        response_post = self.client.post(reverse('apply_center'), {'name': 'ISKCON Test'})
        self.assertEqual(response_post.status_code, 302)
        self.assertIn('/login/', response_post.url)

    def test_authenticated_user_can_submit_application(self):
        self.client.login(username='applicant_bhakta', password='Password@123')
        response = self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Ahmedabad',
            'code': 'iskcon-ahmedabad',
            'city': 'Ahmedabad',
            'state': 'Gujarat',
            'country': 'India',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('apply_center'))

        center = Center.objects.filter(code='iskcon-ahmedabad').first()
        self.assertIsNotNone(center)
        self.assertEqual(center.name, 'ISKCON Ahmedabad')
        self.assertEqual(center.status, 'PENDING')
        self.assertEqual(center.submitted_by, self.applicant)
        self.assertIsNone(center.approved_by)
        self.assertIsNone(center.approved_at)

        # Check that it appears in user's submission history
        get_response = self.client.get(reverse('apply_center'))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'ISKCON Ahmedabad')
        self.assertContains(get_response, 'Pending Review')

    def test_auto_slug_generation_when_code_left_blank(self):
        self.client.login(username='applicant_bhakta', password='Password@123')
        response = self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Vrindavan Dham',
            'code': '',
            'city': 'Vrindavan',
            'state': 'Uttar Pradesh',
            'country': 'India',
        })
        self.assertEqual(response.status_code, 302)

        center = Center.objects.filter(name='ISKCON Vrindavan Dham').first()
        self.assertIsNotNone(center)
        self.assertEqual(center.code, 'iskcon-vrindavan-dham')
        self.assertEqual(center.status, 'PENDING')

    def test_duplicate_center_name_rejected(self):
        self.client.login(username='applicant_bhakta', password='Password@123')
        # Shantipur already exists as APPROVED
        response = self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Shantipur',
            'code': 'new-shantipur',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('already registered', str(response.context['form'].errors['name']))

    def test_duplicate_pending_application_rejected(self):
        # Create pending application
        Center.objects.create(
            name='ISKCON Kanpur',
            code='iskcon-kanpur',
            status='PENDING',
            submitted_by=self.applicant
        )

        self.client.login(username='applicant_bhakta', password='Password@123')
        response = self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Kanpur',
            'code': 'iskcon-kanpur-2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('already pending review', str(response.context['form'].errors['name']))

    def test_duplicate_code_slug_rejected(self):
        self.client.login(username='applicant_bhakta', password='Password@123')
        # Code 'shantipur' is already taken
        response = self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Nadia',
            'code': 'shantipur',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['form'].is_valid())
        self.assertIn('already taken', str(response.context['form'].errors['code']))

    def test_non_platform_admin_cannot_access_review_queue(self):
        # 1. Regular user gets 403
        self.client.login(username='regular_devotee', password='Password@123')
        response = self.client.get(reverse('center_applications_list'))
        self.assertEqual(response.status_code, 403)

        # 2. Center Manager (not platform admin) also gets 403
        self.client.login(username='shantipur_manager', password='Password@123')
        response = self.client.get(reverse('center_applications_list'))
        self.assertEqual(response.status_code, 403)

    def test_non_platform_admin_cannot_approve_or_reject_application(self):
        pending_center = Center.objects.create(
            name='ISKCON Delhi',
            code='iskcon-delhi',
            status='PENDING',
            submitted_by=self.applicant
        )

        # Center Manager attempts to approve
        self.client.login(username='shantipur_manager', password='Password@123')
        response = self.client.post(reverse('approve_center_application', args=[pending_center.id]))
        self.assertEqual(response.status_code, 403)

        # Verify center remains pending
        pending_center.refresh_from_db()
        self.assertEqual(pending_center.status, 'PENDING')

        # Regular user attempts to reject
        self.client.login(username='regular_devotee', password='Password@123')
        response = self.client.post(reverse('reject_center_application', args=[pending_center.id]))
        self.assertEqual(response.status_code, 403)

        pending_center.refresh_from_db()
        self.assertEqual(pending_center.status, 'PENDING')

    def test_platform_admin_can_view_review_queue(self):
        Center.objects.create(
            name='ISKCON Puri',
            code='iskcon-puri',
            status='PENDING',
            submitted_by=self.applicant
        )

        self.client.login(username='admin_user', password='Password@123')
        response = self.client.get(reverse('center_applications_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ISKCON Puri')
        self.assertContains(response, 'applicant_bhakta')

    def test_platform_admin_can_approve_application_and_grants_manager_role(self):
        pending_center = Center.objects.create(
            name='ISKCON Ujjain',
            code='iskcon-ujjain',
            status='PENDING',
            submitted_by=self.applicant
        )

        self.client.login(username='admin_user', password='Password@123')
        response = self.client.post(reverse('approve_center_application', args=[pending_center.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('center_applications_list'))

        # Check center is activated
        pending_center.refresh_from_db()
        self.assertEqual(pending_center.status, 'APPROVED')
        self.assertTrue(pending_center.is_approved)
        self.assertEqual(pending_center.approved_by, self.admin)
        self.assertIsNotNone(pending_center.approved_at)

        # Check applicant is now Center Manager
        membership = CenterMembership.objects.filter(center=pending_center, user=self.applicant).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'MANAGER')
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.is_manager)

    def test_platform_admin_can_reject_application(self):
        pending_center = Center.objects.create(
            name='ISKCON Jaipur',
            code='iskcon-jaipur',
            status='PENDING',
            submitted_by=self.applicant
        )

        self.client.login(username='admin_user', password='Password@123')
        response = self.client.post(reverse('reject_center_application', args=[pending_center.id]))
        self.assertEqual(response.status_code, 302)

        pending_center.refresh_from_db()
        self.assertEqual(pending_center.status, 'REJECTED')
        self.assertFalse(pending_center.is_approved)
        self.assertEqual(pending_center.approved_by, self.admin)

        # Applicant receives no membership
        self.assertFalse(CenterMembership.objects.filter(center=pending_center, user=self.applicant).exists())

    def test_repeated_approval_handled_safely(self):
        center = Center.objects.create(
            name='ISKCON Hyderabad',
            code='iskcon-hyderabad',
            status='APPROVED',
            submitted_by=self.applicant
        )
        self.client.login(username='admin_user', password='Password@123')
        response = self.client.post(reverse('approve_center_application', args=[center.id]))
        self.assertEqual(response.status_code, 302)
        # Status remains unchanged, no crash
        center.refresh_from_db()
        self.assertEqual(center.status, 'APPROVED')

    def test_approved_applicant_can_access_dashboard_and_add_expense(self):
        # 1. Applicant submits
        self.client.login(username='applicant_bhakta', password='Password@123')
        self.client.post(reverse('apply_center'), {
            'name': 'ISKCON Kolkata',
            'code': 'iskcon-kolkata',
            'city': 'Kolkata',
        })
        kolkata = Center.objects.get(code='iskcon-kolkata')

        # Applicant cannot access dashboard for pending center (active_center remains None)
        response = self.client.get(f"{reverse('dashboard')}?center={kolkata.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['active_center'])

        # 2. Admin approves
        self.client.login(username='admin_user', password='Password@123')
        self.client.post(reverse('approve_center_application', args=[kolkata.id]))

        # 3. Applicant can now access dashboard and add expenses
        self.client.login(username='applicant_bhakta', password='Password@123')
        response = self.client.get(f"{reverse('dashboard')}?center={kolkata.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ISKCON Kolkata')
        self.assertContains(response, 'Center Manager')

        # Applicant adds an expense for ISKCON Kolkata
        create_res = self.client.post(reverse('addpost'), {
            'center': kolkata.id,
            'category': 'Kitchen Food',
            'amount_taken': 3000,
            'amount_used': 2500,
            'desc': 'Prasadam ingredients for Kolkata opening',
        })
        self.assertEqual(create_res.status_code, 302)
        expense = Post.objects.filter(center=kolkata).first()
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount_taken, 3000)
        self.assertEqual(expense.user, self.applicant)


class CenterMembershipManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Platform Admin
        self.superadmin = User.objects.create_superuser(
            username='platform_superadmin', password='Password@123', email='superadmin@iskcon.org'
        )

        # Center A
        self.center_a, _ = Center.objects.get_or_create(
            code='center-a',
            defaults={'name': 'ISKCON Center A', 'status': 'APPROVED', 'country': 'India'}
        )
        self.manager_a = User.objects.create_user(
            username='manager_a', password='Password@123', email='manager_a@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_a, user=self.manager_a, role='MANAGER', is_active=True
        )

        self.volunteer_a = User.objects.create_user(
            username='volunteer_a', password='Password@123', email='volunteer_a@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_a, user=self.volunteer_a, role='VOLUNTEER', is_active=True
        )

        # Center B
        self.center_b, _ = Center.objects.get_or_create(
            code='center-b',
            defaults={'name': 'ISKCON Center B', 'status': 'APPROVED', 'country': 'India'}
        )
        self.manager_b = User.objects.create_user(
            username='manager_b', password='Password@123', email='manager_b@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_b, user=self.manager_b, role='MANAGER', is_active=True
        )

        # External user with no memberships
        self.devotee_external = User.objects.create_user(
            username='devotee_external', password='Password@123', email='external@iskcon.org', first_name='External Devotee'
        )

    def test_manager_can_view_own_center_members_page(self):
        self.client.login(username='manager_a', password='Password@123')
        response = self.client.get(reverse('center_members', args=[self.center_a.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ISKCON Center A')
        self.assertContains(response, 'volunteer_a')

    def test_manager_cannot_view_or_manage_other_center_members(self):
        self.client.login(username='manager_a', password='Password@123')
        # Manager A tries to view Center B members
        response = self.client.get(reverse('center_members', args=[self.center_b.id]))
        self.assertEqual(response.status_code, 403)

    def test_volunteer_cannot_access_members_management(self):
        self.client.login(username='volunteer_a', password='Password@123')
        response = self.client.get(reverse('center_members', args=[self.center_a.id]))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_invite_volunteer_by_email(self):
        self.client.login(username='manager_a', password='Password@123')
        response = self.client.post(reverse('invite_volunteer', args=[self.center_a.id]), {
            'email': 'new_devotee@example.com',
            'role': 'VOLUNTEER',
        })
        self.assertEqual(response.status_code, 302)

        invitation = CenterInvitation.objects.filter(center=self.center_a, email='new_devotee@example.com').first()
        self.assertIsNotNone(invitation)
        self.assertEqual(invitation.role, 'VOLUNTEER')
        self.assertEqual(invitation.invited_by, self.manager_a)
        self.assertEqual(invitation.status, 'PENDING')
        self.assertTrue(invitation.is_valid())
        self.assertFalse(invitation.is_expired)
        self.assertIsNotNone(invitation.token)

    def test_manager_cannot_invite_to_other_center(self):
        self.client.login(username='manager_a', password='Password@123')
        response = self.client.post(reverse('invite_volunteer', args=[self.center_b.id]), {
            'email': 'intruder@example.com',
            'role': 'VOLUNTEER',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CenterInvitation.objects.filter(email='intruder@example.com').exists())

    def test_signup_with_valid_invitation_grants_membership_and_consumes_token(self):
        invitation = CenterInvitation.objects.create(
            center=self.center_a,
            email='bhaktin_priya@example.com',
            role='VOLUNTEER',
            invited_by=self.manager_a,
        )

        response = self.client.post(f"{reverse('signup')}?invitation={invitation.token}", {
            'username': 'bhaktin_priya',
            'email': 'bhaktin_priya@example.com',
            'first_name': 'Priya',
            'last_name': 'Devi',
            'password1': 'Password@123',
            'password2': 'Password@123',
            'invitation_token': invitation.token,
        })
        self.assertEqual(response.status_code, 302)

        # Check new user created
        new_user = User.objects.filter(username='bhaktin_priya').first()
        self.assertIsNotNone(new_user)

        # Check token is consumed (single-use)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'ACCEPTED')
        self.assertEqual(invitation.accepted_by, new_user)
        self.assertIsNotNone(invitation.accepted_at)

        # Check membership granted
        membership = CenterMembership.objects.filter(center=self.center_a, user=new_user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'VOLUNTEER')
        self.assertTrue(membership.is_active)

    def test_signup_without_token_does_not_grant_membership_even_with_invited_email(self):
        CenterInvitation.objects.create(
            center=self.center_a,
            email='someone_invited@example.com',
            role='VOLUNTEER',
            invited_by=self.manager_a,
        )

        # User signs up normally at /signup/ WITHOUT invitation token
        response = self.client.post(reverse('signup'), {
            'username': 'uninvited_signer',
            'email': 'someone_invited@example.com',
            'first_name': 'Sneaky',
            'last_name': 'User',
            'password1': 'Password@123',
            'password2': 'Password@123',
        })
        self.assertEqual(response.status_code, 302)

        user = User.objects.filter(username='uninvited_signer').first()
        self.assertIsNotNone(user)

        # Must NOT be granted center membership
        self.assertFalse(CenterMembership.objects.filter(center=self.center_a, user=user).exists())

    def test_expired_invitation_cannot_be_accepted(self):
        expired_invitation = CenterInvitation.objects.create(
            center=self.center_a,
            email='expired_person@example.com',
            role='VOLUNTEER',
            invited_by=self.manager_a,
            expires_at=now() - timedelta(days=2),
        )
        self.assertTrue(expired_invitation.is_expired)

        # Trying to signup with expired token
        response = self.client.post(f"{reverse('signup')}?invitation={expired_invitation.token}", {
            'username': 'expired_user',
            'email': 'expired_person@example.com',
            'password1': 'Password@123',
            'password2': 'Password@123',
            'invitation_token': expired_invitation.token,
        })
        # Signup succeeds as normal account but token is not consumed and NO membership is granted
        user = User.objects.filter(username='expired_user').first()
        if user:
            self.assertFalse(CenterMembership.objects.filter(center=self.center_a, user=user).exists())

        expired_invitation.refresh_from_db()
        self.assertNotEqual(expired_invitation.status, 'ACCEPTED')

    def test_revoked_invitation_cannot_be_accepted(self):
        invitation = CenterInvitation.objects.create(
            center=self.center_a,
            email='revoked_invite@example.com',
            role='VOLUNTEER',
            invited_by=self.manager_a,
            status='REVOKED',
        )

        self.client.login(username='devotee_external', password='Password@123')
        response = self.client.post(reverse('view_invitation', args=[invitation.token]))
        self.assertFalse(CenterMembership.objects.filter(center=self.center_a, user=self.devotee_external).exists())

    def test_single_use_invitation_cannot_be_reused(self):
        invitation = CenterInvitation.objects.create(
            center=self.center_a,
            email='external@iskcon.org',
            role='VOLUNTEER',
            invited_by=self.manager_a,
        )

        # User 1 accepts
        self.client.login(username='devotee_external', password='Password@123')
        self.client.post(reverse('view_invitation', args=[invitation.token]))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'ACCEPTED')

        # User 2 attempts to use same token
        other_user = User.objects.create_user(
            username='second_claimant', password='Password@123', email='second@example.com'
        )
        self.client.login(username='second_claimant', password='Password@123')
        self.client.post(reverse('view_invitation', args=[invitation.token]))

        # Second user does NOT get membership
        self.assertFalse(CenterMembership.objects.filter(center=self.center_a, user=other_user).exists())

    def test_authenticated_user_can_accept_invitation_directly(self):
        invitation = CenterInvitation.objects.create(
            center=self.center_a,
            email='external@iskcon.org',
            role='IN_CHARGE',
            invited_by=self.manager_a,
        )

        self.client.login(username='devotee_external', password='Password@123')
        response = self.client.post(reverse('view_invitation', args=[invitation.token]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'ACCEPTED')
        self.assertEqual(invitation.accepted_by, self.devotee_external)

        membership = CenterMembership.objects.filter(center=self.center_a, user=self.devotee_external).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'IN_CHARGE')

    def test_manager_can_search_user_and_grant_membership(self):
        self.client.login(username='manager_a', password='Password@123')

        # 1. Search for existing account
        search_res = self.client.get(f"{reverse('center_members', args=[self.center_a.id])}?search_username=devotee_external")
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, 'devotee_external')
        # Ensure private emails are not exposed in search results
        self.assertNotContains(search_res, 'external@iskcon.org')

        # 2. Grant membership
        grant_res = self.client.post(reverse('grant_user_membership', args=[self.center_a.id]), {
            'user_id': self.devotee_external.id,
            'role': 'IN_CHARGE',
        })
        self.assertEqual(grant_res.status_code, 302)

        membership = CenterMembership.objects.filter(center=self.center_a, user=self.devotee_external).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'IN_CHARGE')
        self.assertTrue(membership.is_active)

    def test_manager_can_revoke_and_reactivate_membership(self):
        self.client.login(username='manager_a', password='Password@123')
        volunteer_membership = CenterMembership.objects.get(center=self.center_a, user=self.volunteer_a)
        self.assertTrue(volunteer_membership.is_active)

        # Revoke
        revoke_res = self.client.post(reverse('revoke_user_membership', args=[self.center_a.id, volunteer_membership.id]))
        self.assertEqual(revoke_res.status_code, 302)
        volunteer_membership.refresh_from_db()
        self.assertFalse(volunteer_membership.is_active)

        # Reactivate
        reactivate_res = self.client.post(reverse('reactivate_user_membership', args=[self.center_a.id, volunteer_membership.id]))
        self.assertEqual(reactivate_res.status_code, 302)
        volunteer_membership.refresh_from_db()
        self.assertTrue(volunteer_membership.is_active)

    def test_manager_cannot_revoke_own_membership(self):
        self.client.login(username='manager_a', password='Password@123')
        own_membership = CenterMembership.objects.get(center=self.center_a, user=self.manager_a)

        response = self.client.post(reverse('revoke_user_membership', args=[self.center_a.id, own_membership.id]))
        self.assertEqual(response.status_code, 302)
        own_membership.refresh_from_db()
        # Self-revocation blocked: membership remains active
        self.assertTrue(own_membership.is_active)

    def test_manager_can_change_member_role(self):
        self.client.login(username='manager_a', password='Password@123')
        volunteer_membership = CenterMembership.objects.get(center=self.center_a, user=self.volunteer_a)
        self.assertEqual(volunteer_membership.role, 'VOLUNTEER')

        response = self.client.post(reverse('change_member_role', args=[self.center_a.id, volunteer_membership.id]), {
            'role': 'IN_CHARGE'
        })
        self.assertEqual(response.status_code, 302)
        volunteer_membership.refresh_from_db()
        self.assertEqual(volunteer_membership.role, 'IN_CHARGE')


class CenterExpenseWorkflowAndSettlementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Center A
        self.center_a, _ = Center.objects.get_or_create(
            code='center-a-exp',
            defaults={'name': 'Center A Expenses', 'status': 'APPROVED', 'country': 'India'}
        )
        self.in_charge_a = User.objects.create_user(
            username='in_charge_a', password='Password@123', email='incharge_a@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_a, user=self.in_charge_a, role='IN_CHARGE', is_active=True
        )

        self.manager_a = User.objects.create_user(
            username='manager_exp_a', password='Password@123', email='manager_exp_a@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_a, user=self.manager_a, role='MANAGER', is_active=True
        )

        self.volunteer_a = User.objects.create_user(
            username='volunteer_exp_a', password='Password@123', email='vol_exp_a@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_a, user=self.volunteer_a, role='VOLUNTEER', is_active=True
        )

        # Center B
        self.center_b, _ = Center.objects.get_or_create(
            code='center-b-exp',
            defaults={'name': 'Center B Expenses', 'status': 'APPROVED', 'country': 'India'}
        )
        self.in_charge_b = User.objects.create_user(
            username='in_charge_b', password='Password@123', email='incharge_b@iskcon.org'
        )
        CenterMembership.objects.create(
            center=self.center_b, user=self.in_charge_b, role='IN_CHARGE', is_active=True
        )

        # Unsettled expense in Center A
        self.expense_a = Post.objects.create(
            center=self.center_a,
            user=self.volunteer_a,
            category='Kitchen Food',
            amount_taken=2000,
            amount_used=1500,
            desc='Rice and vegetables',
            remaining=False,
            status=True,
        )

        # Unsettled expense in Center B
        self.expense_b = Post.objects.create(
            center=self.center_b,
            user=self.in_charge_b,
            category='Petrol',
            amount_taken=1000,
            amount_used=800,
            desc='Travel',
            remaining=False,
            status=True,
        )

    def test_member_can_add_expense_only_to_own_center(self):
        self.client.login(username='volunteer_exp_a', password='Password@123')

        # 1. Successful creation in Center A
        response = self.client.post(reverse('addpost'), {
            'center': self.center_a.id,
            'category': 'Kitchen Food',
            'amount_taken': 500,
            'amount_used': 450,
            'desc': 'Ghee purchase',
        })
        self.assertEqual(response.status_code, 302)
        created_post = Post.objects.filter(center=self.center_a, desc='Ghee purchase').first()
        self.assertIsNotNone(created_post)
        self.assertEqual(created_post.user, self.volunteer_a)
        self.assertFalse(created_post.remaining)
        self.assertEqual(created_post.to_be_returned, 50)

        # 2. Blocked creation in Center B
        bad_response = self.client.post(reverse('addpost'), {
            'center': self.center_b.id,
            'category': 'Petrol',
            'amount_taken': 500,
            'amount_used': 500,
            'desc': 'Unauthorized Center B expense',
        })
        self.assertIn(bad_response.status_code, [200, 403])
        self.assertFalse(Post.objects.filter(desc='Unauthorized Center B expense').exists())

    def test_center_in_charge_can_settle_expense_with_audit_trail(self):
        self.client.login(username='in_charge_a', password='Password@123')
        self.assertFalse(self.expense_a.remaining)
        self.assertIsNone(self.expense_a.settled_by)
        self.assertIsNone(self.expense_a.settled_at)

        response = self.client.post(reverse('settle_expense', args=[self.expense_a.id]))
        self.assertEqual(response.status_code, 302)

        self.expense_a.refresh_from_db()
        self.assertTrue(self.expense_a.remaining)
        self.assertEqual(self.expense_a.settled_by, self.in_charge_a)
        self.assertIsNotNone(self.expense_a.settled_at)
        # Mathematical meaning of remaining and to_be_returned preserved
        self.assertEqual(self.expense_a.to_be_returned, 500)

    def test_center_manager_can_also_settle_expense(self):
        self.client.login(username='manager_exp_a', password='Password@123')
        response = self.client.post(reverse('settle_expense', args=[self.expense_a.id]))
        self.assertEqual(response.status_code, 302)

        self.expense_a.refresh_from_db()
        self.assertTrue(self.expense_a.remaining)
        self.assertEqual(self.expense_a.settled_by, self.manager_a)
        self.assertIsNotNone(self.expense_a.settled_at)

    def test_volunteer_cannot_settle_expense(self):
        self.client.login(username='volunteer_exp_a', password='Password@123')
        response = self.client.post(reverse('settle_expense', args=[self.expense_a.id]))
        self.assertEqual(response.status_code, 403)

        self.expense_a.refresh_from_db()
        self.assertFalse(self.expense_a.remaining)
        self.assertIsNone(self.expense_a.settled_by)
        self.assertIsNone(self.expense_a.settled_at)

    def test_cross_center_settlement_denied(self):
        # In-charge of Center A tries to settle an expense in Center B
        self.client.login(username='in_charge_a', password='Password@123')
        response = self.client.post(reverse('settle_expense', args=[self.expense_b.id]))
        self.assertEqual(response.status_code, 403)

        self.expense_b.refresh_from_db()
        self.assertFalse(self.expense_b.remaining)
        self.assertIsNone(self.expense_b.settled_by)

    def test_prevent_accidental_repeat_settlement(self):
        # 1. Settle first by in_charge_a
        self.expense_a.settle(self.in_charge_a)
        original_settler = self.expense_a.settled_by
        original_time = self.expense_a.settled_at

        # 2. Another manager attempts repeat settlement
        self.client.login(username='manager_exp_a', password='Password@123')
        response = self.client.post(reverse('settle_expense', args=[self.expense_a.id]))
        self.assertEqual(response.status_code, 302)

        self.expense_a.refresh_from_db()
        # Audit trail must NOT be overwritten!
        self.assertEqual(self.expense_a.settled_by, original_settler)
        self.assertEqual(self.expense_a.settled_at, original_time)

    def test_get_request_to_settle_expense_does_not_settle(self):
        self.client.login(username='in_charge_a', password='Password@123')
        # GET request
        response = self.client.get(reverse('settle_expense', args=[self.expense_a.id]))
        self.assertEqual(response.status_code, 302)

        self.expense_a.refresh_from_db()
        self.assertFalse(self.expense_a.remaining)
        self.assertIsNone(self.expense_a.settled_by)

    def test_settle_via_update_post_records_audit_trail_for_in_charge(self):
        self.client.login(username='in_charge_a', password='Password@123')
        response = self.client.post(reverse('updatepost', args=[self.expense_a.id]), {
            'category': 'Kitchen Food',
            'amount_taken': 2000,
            'amount_used': 1500,
            'desc': 'Rice and vegetables - settled via edit',
            'remaining': True,
        })
        self.assertEqual(response.status_code, 302)

        self.expense_a.refresh_from_db()
        self.assertTrue(self.expense_a.remaining)
        self.assertEqual(self.expense_a.settled_by, self.in_charge_a)
        self.assertIsNotNone(self.expense_a.settled_at)

    def test_dashboard_settlement_filters_for_in_charge(self):
        self.client.login(username='in_charge_a', password='Password@123')

        # Filter: unsettled
        res_unsettled = self.client.get(f"{reverse('dashboard')}?center={self.center_a.id}&settlement=unsettled")
        self.assertEqual(res_unsettled.status_code, 200)
        self.assertContains(res_unsettled, self.expense_a.desc)

        # Settle it
        self.expense_a.settle(self.in_charge_a)

        # Filter: unsettled now does not contain it
        res_unsettled2 = self.client.get(f"{reverse('dashboard')}?center={self.center_a.id}&settlement=unsettled")
        self.assertEqual(res_unsettled2.status_code, 200)
        self.assertNotContains(res_unsettled2, self.expense_a.desc)

        # Filter: settled contains it
        res_settled = self.client.get(f"{reverse('dashboard')}?center={self.center_a.id}&settlement=settled")
        self.assertEqual(res_settled.status_code, 200)
        self.assertContains(res_settled, self.expense_a.desc)


class BulkSettlementWorkflowTests(TestCase):
    def setUp(self):
        self.center_a = Center.objects.create(name='ISKCON Mayapur', code='mayapur', status='APPROVED')
        self.center_b = Center.objects.create(name='ISKCON Vrindavan', code='vrindavan', status='APPROVED')

        self.in_charge_a = User.objects.create_user(username='in_charge_a', password='Password@123')
        CenterMembership.objects.create(center=self.center_a, user=self.in_charge_a, role='IN_CHARGE')

        self.volunteer_a = User.objects.create_user(username='volunteer_a', password='Password@123')
        CenterMembership.objects.create(center=self.center_a, user=self.volunteer_a, role='VOLUNTEER')

        self.volunteer_b = User.objects.create_user(username='volunteer_b', password='Password@123')
        CenterMembership.objects.create(center=self.center_b, user=self.volunteer_b, role='VOLUNTEER')

        # Create multiple expenses in center A
        self.expense_a1 = Post.objects.create(
            center=self.center_a, user=self.volunteer_a, category='Kitchen Food',
            amount_taken=1000, amount_used=800, desc='Flour and sugar', remaining=False
        )
        self.expense_a2 = Post.objects.create(
            center=self.center_a, user=self.volunteer_a, category='Petrol',
            amount_taken=500, amount_used=500, desc='Fuel for van', remaining=False
        )
        self.expense_a3 = Post.objects.create(
            center=self.center_a, user=self.volunteer_a, category='Necessities',
            amount_taken=200, amount_used=200, desc='Cleaning supplies', remaining=False
        )

        # Expense in center B
        self.expense_b1 = Post.objects.create(
            center=self.center_b, user=self.volunteer_b, category='Kitchen Food',
            amount_taken=600, amount_used=600, desc='Milk', remaining=False
        )

    def test_in_charge_can_bulk_settle_multiple_expenses(self):
        self.client.login(username='in_charge_a', password='Password@123')
        response = self.client.post(reverse('bulk_settle_expenses'), {
            'post_ids': [self.expense_a1.id, self.expense_a2.id],
            'next': reverse('dashboard'),
        })
        self.assertEqual(response.status_code, 302)

        self.expense_a1.refresh_from_db()
        self.expense_a2.refresh_from_db()
        self.expense_a3.refresh_from_db()

        self.assertTrue(self.expense_a1.remaining)
        self.assertEqual(self.expense_a1.settled_by, self.in_charge_a)
        self.assertIsNotNone(self.expense_a1.settled_at)

        self.assertTrue(self.expense_a2.remaining)
        self.assertEqual(self.expense_a2.settled_by, self.in_charge_a)

        # Non-selected expense remains unsettled
        self.assertFalse(self.expense_a3.remaining)
        self.assertIsNone(self.expense_a3.settled_by)

    def test_bulk_settle_skips_already_settled_expenses_safely(self):
        # Pre-settle a1
        self.expense_a1.settle(self.in_charge_a)
        original_time = self.expense_a1.settled_at

        self.client.login(username='in_charge_a', password='Password@123')
        response = self.client.post(reverse('bulk_settle_expenses'), {
            'post_ids': [self.expense_a1.id, self.expense_a2.id],
        })
        self.assertEqual(response.status_code, 302)

        self.expense_a1.refresh_from_db()
        self.expense_a2.refresh_from_db()

        # a1 original audit intact
        self.assertEqual(self.expense_a1.settled_at, original_time)
        # a2 newly settled
        self.assertTrue(self.expense_a2.remaining)
        self.assertEqual(self.expense_a2.settled_by, self.in_charge_a)

    def test_bulk_settle_denied_for_volunteer(self):
        self.client.login(username='volunteer_a', password='Password@123')
        response = self.client.post(reverse('bulk_settle_expenses'), {
            'post_ids': [self.expense_a1.id],
        })
        self.assertEqual(response.status_code, 403)

        self.expense_a1.refresh_from_db()
        self.assertFalse(self.expense_a1.remaining)

    def test_bulk_settle_denied_for_cross_center_tampering(self):
        # In-charge of A tries to include an expense from B
        self.client.login(username='in_charge_a', password='Password@123')
        response = self.client.post(reverse('bulk_settle_expenses'), {
            'post_ids': [self.expense_a1.id, self.expense_b1.id],
        })
        self.assertEqual(response.status_code, 403)

        # Transaction rollback ensures neither was settled
        self.expense_a1.refresh_from_db()
        self.expense_b1.refresh_from_db()
        self.assertFalse(self.expense_a1.remaining)
        self.assertFalse(self.expense_b1.remaining)


class NavigationAndTemplateRenderingTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username='admin_boss', password='Password@123'
        )
        self.center_a = Center.objects.create(name='ISKCON Pune', code='pune', status='APPROVED')
        self.center_b = Center.objects.create(name='ISKCON Delhi', code='delhi', status='APPROVED')

        # Manager user with multiple centers
        self.multi_mgr = User.objects.create_user(username='multi_mgr', password='Password@123')
        CenterMembership.objects.create(center=self.center_a, user=self.multi_mgr, role='MANAGER')
        CenterMembership.objects.create(center=self.center_b, user=self.multi_mgr, role='IN_CHARGE')

        # Single-center member
        self.single_user = User.objects.create_user(username='single_user', password='Password@123')
        CenterMembership.objects.create(center=self.center_a, user=self.single_user, role='VOLUNTEER')

        # User with no centers
        self.lonely_user = User.objects.create_user(username='lonely_user', password='Password@123')

    def test_navbar_multi_center_dropdown(self):
        self.client.login(username='multi_mgr', password='Password@123')
        # In Pune, multi_mgr is MANAGER
        response = self.client.get(f"{reverse('dashboard')}?center={self.center_a.id}")
        self.assertEqual(response.status_code, 200)
        # Should render dropdown toggle with active center
        self.assertContains(response, 'Switch Active Center')
        self.assertContains(response, 'ISKCON Pune')
        self.assertContains(response, 'ISKCON Delhi')
        # Manager in Pune sees Members & Invites
        self.assertContains(response, 'Members &amp; Invites')

        # In Delhi, multi_mgr is IN_CHARGE (can settle, but cannot manage members)
        res_delhi = self.client.get(f"{reverse('dashboard')}?center={self.center_b.id}")
        self.assertEqual(res_delhi.status_code, 200)
        self.assertContains(res_delhi, 'Review &amp; Settle')
        self.assertNotContains(res_delhi, 'Members &amp; Invites')

    def test_navbar_single_center_badge(self):
        self.client.login(username='single_user', password='Password@123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ISKCON Pune')
        self.assertNotContains(response, 'Switch Active Center')
        # Volunteers should not see settlement or member admin links in navbar
        self.assertNotContains(response, 'Review &amp; Settle')
        self.assertNotContains(response, 'Members &amp; Invites')

    def test_navbar_no_center_badge(self):
        self.client.login(username='lonely_user', password='Password@123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Center Assigned')

    def test_platform_admin_sees_platform_review_link(self):
        self.client.login(username='admin_boss', password='Password@123')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Platform: Review Applications')

    def test_dashboard_empty_state_no_centers(self):
        self.client.login(username='lonely_user', password='Password@123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Active Center Selected')
        self.assertContains(response, reverse('apply_center'))
        self.assertContains(response, reverse('my_center_applications'))

    def test_dashboard_empty_state_all_caught_up(self):
        self.client.login(username='multi_mgr', password='Password@123')
        # Empty center, unsettled filter
        response = self.client.get(f"{reverse('dashboard')}?center={self.center_a.id}&settlement=unsettled")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'All Caught Up!')

    def test_custom_403_template_renders_on_permission_denied(self):
        self.client.login(username='single_user', password='Password@123')
        # Attempt to access member management (only manager allowed)
        response = self.client.get(reverse('center_members', args=[self.center_a.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')
        self.assertContains(response, '403 - Permission Denied', status_code=403)


class SecurityAuditAndRegressionTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username='sec_admin', password='Password@123', email='sec_admin@iskcon.org'
        )
        self.center_x = Center.objects.create(name='Center X Kolkata', code='center-x', status='APPROVED')
        self.center_y = Center.objects.create(name='Center Y Chennai', code='center-y', status='APPROVED')

        self.manager_x = User.objects.create_user(
            username='mgr_x', password='Password@123', email='mgr_x@iskcon.org'
        )
        CenterMembership.objects.create(center=self.center_x, user=self.manager_x, role='MANAGER')

        self.volunteer_x = User.objects.create_user(
            username='vol_x', password='Password@123', email='vol_x@iskcon.org'
        )
        CenterMembership.objects.create(center=self.center_x, user=self.volunteer_x, role='VOLUNTEER')

        self.manager_y = User.objects.create_user(
            username='mgr_y', password='Password@123', email='mgr_y@iskcon.org'
        )
        CenterMembership.objects.create(center=self.center_y, user=self.manager_y, role='MANAGER')

        self.volunteer_y = User.objects.create_user(
            username='vol_y', password='Password@123', email='vol_y@iskcon.org'
        )
        self.membership_y = CenterMembership.objects.create(
            center=self.center_y, user=self.volunteer_y, role='VOLUNTEER'
        )

        # Expenses
        self.expense_x = Post.objects.create(
            center=self.center_x, user=self.volunteer_x, category='Petrol',
            amount_taken=1000, amount_used=800, desc='Kolkata patrol', remaining=False
        )
        self.expense_y = Post.objects.create(
            center=self.center_y, user=self.volunteer_y, category='Kitchen Food',
            amount_taken=2000, amount_used=1500, desc='Chennai prasadam', remaining=False
        )

    def test_user_cannot_view_edit_delete_settle_expense_in_another_center(self):
        self.client.login(username='mgr_x', password='Password@123')

        # 1. Edit expense in Center Y -> 403
        edit_res = self.client.post(reverse('updatepost', args=[self.expense_y.id]), {
            'category': 'Kitchen Food', 'amount_taken': 2000, 'amount_used': 1500, 'desc': 'Tampered'
        })
        self.assertEqual(edit_res.status_code, 403)
        self.expense_y.refresh_from_db()
        self.assertEqual(self.expense_y.desc, 'Chennai prasadam')

        # 2. Delete expense in Center Y -> 403
        del_res = self.client.post(reverse('deletepost', args=[self.expense_y.id]))
        self.assertEqual(del_res.status_code, 403)
        self.assertTrue(Post.objects.filter(id=self.expense_y.id).exists())

        # 3. Settle expense in Center Y -> 403
        settle_res = self.client.post(reverse('settle_expense', args=[self.expense_y.id]))
        self.assertEqual(settle_res.status_code, 403)
        self.expense_y.refresh_from_db()
        self.assertFalse(self.expense_y.remaining)

        # 4. Bulk settle tampering across centers -> 403
        bulk_res = self.client.post(reverse('bulk_settle_expenses'), {
            'post_ids': [self.expense_x.id, self.expense_y.id]
        })
        self.assertEqual(bulk_res.status_code, 403)
        self.expense_x.refresh_from_db()
        self.expense_y.refresh_from_db()
        self.assertFalse(self.expense_x.remaining)
        self.assertFalse(self.expense_y.remaining)

    def test_create_expense_cannot_assign_unauthorized_center_or_user(self):
        # Volunteer X tries to submit an expense for Center Y
        self.client.login(username='vol_x', password='Password@123')
        res = self.client.post(reverse('addpost'), {
            'center': self.center_y.id,
            'category': 'Petrol',
            'amount_taken': 500,
            'amount_used': 500,
            'desc': 'Sneaky cross center',
        })
        # Volunteer X has active center X, form clean_center rejects center_y
        self.assertFalse(Post.objects.filter(desc='Sneaky cross center').exists())

        # Volunteer X tries to assign expense to manager_x
        res2 = self.client.post(reverse('addpost'), {
            'user': self.manager_x.id,
            'category': 'Petrol',
            'amount_taken': 300,
            'amount_used': 300,
            'desc': 'Assigned to manager',
        })
        created_post = Post.objects.filter(desc='Assigned to manager').first()
        self.assertIsNotNone(created_post)
        # Must be assigned to requesting user, not manager_x
        self.assertEqual(created_post.user, self.volunteer_x)

    def test_manager_cannot_manage_members_in_another_center(self):
        self.client.login(username='mgr_x', password='Password@123')

        # 1. View members of Center Y -> 403
        view_res = self.client.get(reverse('center_members', args=[self.center_y.id]))
        self.assertEqual(view_res.status_code, 403)

        # 2. Grant membership in Center Y -> 403
        grant_res = self.client.post(reverse('grant_user_membership', args=[self.center_y.id]), {
            'user_id': self.volunteer_x.id, 'role': 'IN_CHARGE'
        })
        self.assertEqual(grant_res.status_code, 403)

        # 3. Revoke membership in Center Y -> 403
        revoke_res = self.client.post(reverse('revoke_user_membership', args=[self.center_y.id, self.membership_y.id]))
        self.assertEqual(revoke_res.status_code, 403)
        self.membership_y.refresh_from_db()
        self.assertTrue(self.membership_y.is_active)

        # 4. Cross-center membership ID injection (URL center_x, but membership_id from center_y) -> 404
        cross_res = self.client.post(reverse('revoke_user_membership', args=[self.center_x.id, self.membership_y.id]))
        self.assertEqual(cross_res.status_code, 404)

        # 5. Invite to Center Y -> 403
        invite_res = self.client.post(reverse('invite_volunteer', args=[self.center_y.id]), {
            'email': 'intruder@iskcon.org', 'role': 'VOLUNTEER'
        })
        self.assertEqual(invite_res.status_code, 403)

    def test_platform_admin_vs_center_manager_authority_separation(self):
        # Center Manager cannot access platform admin application queue
        self.client.login(username='mgr_x', password='Password@123')

        queue_res = self.client.get(reverse('center_applications_list'))
        self.assertEqual(queue_res.status_code, 403)

        # Center Manager cannot approve/reject an application
        pending_app = Center.objects.create(name='Pending Bangalore', code='bangalore', status='PENDING')
        appr_res = self.client.post(reverse('approve_center_application', args=[pending_app.id]))
        self.assertEqual(appr_res.status_code, 403)

        rej_res = self.client.post(reverse('reject_center_application', args=[pending_app.id]))
        self.assertEqual(rej_res.status_code, 403)

        # Platform Admin CAN perform these actions
        self.client.login(username='sec_admin', password='Password@123')
        admin_queue = self.client.get(reverse('center_applications_list'))
        self.assertEqual(admin_queue.status_code, 200)

        admin_appr = self.client.post(reverse('approve_center_application', args=[pending_app.id]))
        self.assertEqual(admin_appr.status_code, 302)
        pending_app.refresh_from_db()
        self.assertEqual(pending_app.status, 'APPROVED')
        self.assertEqual(pending_app.approved_by, self.superadmin)

    def test_invitation_cannot_be_accepted_by_unrelated_account_or_reused(self):
        invitation = CenterInvitation.objects.create(
            center=self.center_x,
            email='intended_recipient@iskcon.org',
            role='IN_CHARGE',
            invited_by=self.manager_x,
        )

        # Unrelated user with different email tries to accept -> 403
        unrelated_user = User.objects.create_user(
            username='mallory', password='Password@123', email='mallory@other.org'
        )
        self.client.login(username='mallory', password='Password@123')
        hijack_res = self.client.post(reverse('view_invitation', args=[invitation.token]))
        self.assertEqual(hijack_res.status_code, 403)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'PENDING')
        self.assertFalse(CenterMembership.objects.filter(center=self.center_x, user=unrelated_user).exists())

        # Correct recipient logs in and accepts -> 200/302 Success
        recipient_user = User.objects.create_user(
            username='intended_devotee', password='Password@123', email='intended_recipient@iskcon.org'
        )
        self.client.login(username='intended_devotee', password='Password@123')
        accept_res = self.client.post(reverse('view_invitation', args=[invitation.token]))
        self.assertEqual(accept_res.status_code, 302)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'ACCEPTED')
        self.assertEqual(invitation.accepted_by, recipient_user)

        # Re-using the token fails (single-use proof)
        re_accept_res = self.client.post(reverse('view_invitation', args=[invitation.token]))
        self.assertEqual(re_accept_res.status_code, 200)
        self.assertContains(re_accept_res, 'already been accepted')

    def test_state_changing_endpoints_reject_get_requests(self):
        self.client.login(username='mgr_x', password='Password@123')

        # GET to settle does not settle
        self.client.get(reverse('settle_expense', args=[self.expense_x.id]))
        self.expense_x.refresh_from_db()
        self.assertFalse(self.expense_x.remaining)

        # GET to delete does not delete
        self.client.get(reverse('deletepost', args=[self.expense_x.id]))
        self.assertTrue(Post.objects.filter(id=self.expense_x.id).exists())

        # GET to bulk settle does not settle
        self.client.get(reverse('bulk_settle_expenses'))
        self.expense_x.refresh_from_db()
        self.assertFalse(self.expense_x.remaining)

        # GET to revoke membership does not revoke
        mem_x = CenterMembership.objects.get(center=self.center_x, user=self.volunteer_x)
        self.client.get(reverse('revoke_user_membership', args=[self.center_x.id, mem_x.id]))
        mem_x.refresh_from_db()
        self.assertTrue(mem_x.is_active)


