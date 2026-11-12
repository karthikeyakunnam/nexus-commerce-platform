from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase


class UserAuthenticationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='test-user',
            email='test@example.com',
            password='Strong-password-123',
        )

    def test_registration_rejects_duplicate_username(self):
        response = self.client.post('/api/users/', {
            'username': 'test-user',
            'email': 'other@example.com',
            'password': 'Strong-password-123',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_login_sets_httponly_auth_cookies_and_does_not_return_tokens(self):
        response = self.client.post('/api/token/', {
            'username': 'test-user',
            'password': 'Strong-password-123',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])
