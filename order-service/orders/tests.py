from unittest.mock import Mock, patch
from contextlib import contextmanager

from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from django.test import TestCase

from .models import Order
from .views import OrderViewSet


class OrderIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='buyer', password='Strong-password-123')
        self.factory = APIRequestFactory()

    @contextmanager
    def _client(self):
        user_client = Mock()
        user_client.validate_user.return_value = {'valid': True, 'error_message': ''}
        product_client = Mock()
        product_client.get_product_info.return_value = {
            'exists': True,
            'product_info': {
                'id': 1,
                'name': 'Test product',
                'description': '',
                'price': '12.50',
                'inventory_count': 10,
                'is_available': True,
            },
        }
        product_client.reserve_stock.return_value = {
            'reserved': True,
            'remaining_quantity': 9,
            'error_message': '',
        }
        with patch('orders.views.get_user_service_client', return_value=user_client), patch(
            'orders.views.get_product_service_client', return_value=product_client
        ):
            yield product_client

    def test_retry_returns_existing_order_without_creating_duplicate(self):
        payload = {'items': [{'product_id': 1, 'quantity': 1}]}
        first = self.factory.post('/api/orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY='checkout-1')
        force_authenticate(first, user=self.user)
        with self._client():
            first_response = OrderViewSet.as_view({'post': 'create'})(first)

        second = self.factory.post('/api/orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY='checkout-1')
        force_authenticate(second, user=self.user)
        with self._client():
            second_response = OrderViewSet.as_view({'post': 'create'})(second)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Order.objects.filter(user_id=str(self.user.id)).count(), 1)
