from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

class RegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='johndoe', password='Password@123', first_name='John')

    def test_login_view_get(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')

    def test_login_successful(self):
        response = self.client.post(reverse('login'), {
            'username': 'johndoe',
            'password': 'Password@123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dashboard'), response.url)

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'username': 'johndoe',
            'password': 'WrongPassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct username and password')

    def test_logout(self):
        self.client.login(username='johndoe', password='Password@123')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_signup_successful(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.assertTrue(User.objects.filter(username='newuser').exists())
