import os

from django.test import TestCase

from .models import InventoryReservation, Product


class InventoryReservationTests(TestCase):
    def setUp(self):
        os.environ['SERVICE_SECRET'] = 'test-service-secret'
        self.product = Product.objects.create(
            name='Test product',
            description='test',
            price='10.00',
            inventory_count=3,
        )

    def test_reserve_stock_decrements_inventory_and_is_idempotent(self):
        from grpc_server import ProductServiceServicer
        from grpc_generated import product_pb2

        class Context:
            def invocation_metadata(self):
                return [('authorization', 'Bearer test-service-secret')]

            def set_code(self, code):
                self.code = code

            def set_details(self, details):
                self.details = details

        servicer = ProductServiceServicer()
        request = product_pb2.ReserveStockRequest(
            product_id=self.product.id,
            quantity=2,
            order_id='order-1',
            requesting_service='order-service',
        )
        first = servicer.ReserveStock(request, Context())
        second = servicer.ReserveStock(request, Context())

        self.product.refresh_from_db()
        self.assertTrue(first.reserved)
        self.assertTrue(second.reserved)
        self.assertEqual(self.product.inventory_count, 1)
        self.assertEqual(InventoryReservation.objects.count(), 1)

    def test_release_stock_restores_inventory_once(self):
        from grpc_server import ProductServiceServicer
        from grpc_generated import product_pb2

        class Context:
            def invocation_metadata(self):
                return [('authorization', 'Bearer test-service-secret')]

            def set_code(self, code):
                self.code = code

            def set_details(self, details):
                self.details = details

        servicer = ProductServiceServicer()
        reserve = product_pb2.ReserveStockRequest(
            product_id=self.product.id,
            quantity=2,
            order_id='order-2',
            requesting_service='order-service',
        )
        release = product_pb2.ReleaseStockRequest(
            product_id=self.product.id,
            order_id='order-2',
            requesting_service='order-service',
        )
        servicer.ReserveStock(reserve, Context())
        first = servicer.ReleaseStock(release, Context())
        second = servicer.ReleaseStock(release, Context())

        self.product.refresh_from_db()
        self.assertTrue(first.released)
        self.assertTrue(second.released)
        self.assertEqual(self.product.inventory_count, 3)
