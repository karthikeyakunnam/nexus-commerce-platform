"""
gRPC server for ProductService.

Educational Note: This server handles inter-service communication.
OrderService calls these methods to validate products and check inventory.
"""

import os
import sys
import logging
import hmac
import grpc
from concurrent import futures
import time
from django.db import transaction
from django.utils import timezone

# Add Django project to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product_service.settings')
import django
django.setup()

from products.models import Product, InventoryReservation
from grpc_generated import product_pb2, product_pb2_grpc

logger = logging.getLogger(__name__)

# Shared secret for service-to-service authentication
SERVICE_SECRET = os.getenv('SERVICE_SECRET')
if not SERVICE_SECRET:
    raise RuntimeError('SERVICE_SECRET must be configured for ProductService gRPC')


def is_authorized(context):
    metadata = dict(context.invocation_metadata())
    auth_token = metadata.get('authorization', '')
    return hmac.compare_digest(auth_token, f'Bearer {SERVICE_SECRET}')


class ProductServiceServicer(product_pb2_grpc.ProductServiceServicer):
    """
    Implementation of ProductService gRPC API.
    
    Educational Note: This provides product validation and inventory checks
    for OrderService without exposing the database directly.
    """
    
    def GetProductInfo(self, request, context):
        """
        Get product information including price and availability.
        
        Educational Note: OrderService calls this to get product details
        when creating orders. This ensures OrderService never accesses
        ProductService's database directly (service isolation).
        
        Args:
            request: ProductInfoRequest with product_id
            context: gRPC context
        
        Returns:
            ProductInfoResponse with product details
        """
        
        # Verify service authentication
        if not is_authorized(context):
            logger.warning(f"Unauthorized gRPC call from {request.requesting_service}")
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details('Invalid service credentials')
            return product_pb2.ProductInfoResponse(
                exists=False,
                error_message='Unauthorized'
            )
        
        product_id = request.product_id
        requesting_service = request.requesting_service
        
        logger.info(f"gRPC GetProductInfo called by {requesting_service} for product_id={product_id}")
        
        try:
            product = Product.objects.get(id=product_id)
            
            # Educational Note: Convert Decimal to string to avoid precision issues
            # Protocol Buffers don't have a native Decimal type
            product_info = product_pb2.ProductInfo(
                id=product.id,
                name=product.name,
                description=product.description,
                price=str(product.price),  # Decimal → string
                inventory_count=product.inventory_count,
                is_available=product.is_available
            )
            
            logger.info(f"Product {product_id} info returned to {requesting_service}")
            
            return product_pb2.ProductInfoResponse(
                exists=True,
                product_info=product_info
            )
            
        except Product.DoesNotExist:
            logger.warning(f"Product {product_id} not found (requested by {requesting_service})")
            
            return product_pb2.ProductInfoResponse(
                exists=False,
                error_message=f'Product with id {product_id} not found'
            )
            
        except Exception as e:
            logger.error(f"Error getting product {product_id}: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('Internal server error')
            
            return product_pb2.ProductInfoResponse(
                exists=False,
                error_message='Internal server error'
            )
    
    def CheckAvailability(self, request, context):
        """
        Check if sufficient inventory exists for a quantity.
        
        Educational Note: OrderService calls this before creating orders
        to ensure products are in stock. This prevents overselling.
        
        Args:
            request: AvailabilityRequest with product_id and quantity
            context: gRPC context
        
        Returns:
            AvailabilityResponse with availability status
        """
        
        # Verify service authentication
        if not is_authorized(context):
            logger.warning(f"Unauthorized gRPC call from {request.requesting_service}")
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details('Invalid service credentials')
            return product_pb2.AvailabilityResponse(
                available=False,
                available_quantity=0,
                error_message='Unauthorized'
            )
        
        product_id = request.product_id
        quantity = request.quantity
        requesting_service = request.requesting_service
        
        logger.info(f"gRPC CheckAvailability called by {requesting_service} for product_id={product_id}, quantity={quantity}")
        
        try:
            product = Product.objects.get(id=product_id)
            
            # Check if sufficient inventory exists
            available = product.check_availability(quantity)
            
            logger.info(f"Product {product_id} availability check: requested={quantity}, available={product.inventory_count}, result={available}")
            
            return product_pb2.AvailabilityResponse(
                available=available,
                available_quantity=product.inventory_count,
                error_message='' if available else f'Insufficient inventory. Available: {product.inventory_count}, Requested: {quantity}'
            )
            
        except Product.DoesNotExist:
            logger.warning(f"Product {product_id} not found (requested by {requesting_service})")
            
            return product_pb2.AvailabilityResponse(
                available=False,
                available_quantity=0,
                error_message=f'Product with id {product_id} not found'
            )
            
        except Exception as e:
            logger.error(f"Error checking availability for product {product_id}: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('Internal server error')
            
            return product_pb2.AvailabilityResponse(
                available=False,
                available_quantity=0,
                error_message='Internal server error'
            )

    def ReserveStock(self, request, context):
        """Atomically reserve stock with an idempotent order key."""
        if not is_authorized(context):
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details('Invalid service credentials')
            return product_pb2.ReserveStockResponse(reserved=False, error_message='Unauthorized')

        if request.product_id <= 0 or request.quantity <= 0 or not request.order_id:
            return product_pb2.ReserveStockResponse(
                reserved=False,
                error_message='product_id, quantity, and order_id are required',
            )

        try:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(id=request.product_id)
                reservation, created = InventoryReservation.objects.get_or_create(
                    product=product,
                    order_id=request.order_id,
                    defaults={'quantity': request.quantity, 'status': 'reserved'},
                )

                if not created:
                    if reservation.status == 'reserved' and reservation.quantity == request.quantity:
                        return product_pb2.ReserveStockResponse(
                            reserved=True,
                            remaining_quantity=product.inventory_count,
                        )
                    return product_pb2.ReserveStockResponse(
                        reserved=False,
                        remaining_quantity=product.inventory_count,
                        error_message='Reservation key already belongs to a different request',
                    )

                if product.inventory_count < request.quantity:
                    reservation.delete()
                    return product_pb2.ReserveStockResponse(
                        reserved=False,
                        remaining_quantity=product.inventory_count,
                        error_message=(
                            f'Insufficient inventory. Available: {product.inventory_count}, '
                            f'Requested: {request.quantity}'
                        ),
                    )

                product.inventory_count -= request.quantity
                product.save(update_fields=['inventory_count', 'updated_at'])
                return product_pb2.ReserveStockResponse(
                    reserved=True,
                    remaining_quantity=product.inventory_count,
                )
        except Product.DoesNotExist:
            return product_pb2.ReserveStockResponse(
                reserved=False,
                error_message=f'Product {request.product_id} not found',
            )
        except Exception:
            logger.exception('Error reserving stock for product %s', request.product_id)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('Internal server error')
            return product_pb2.ReserveStockResponse(reserved=False, error_message='Internal server error')

    def ReleaseStock(self, request, context):
        """Release a reservation exactly once."""
        if not is_authorized(context):
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details('Invalid service credentials')
            return product_pb2.ReleaseStockResponse(released=False, error_message='Unauthorized')

        try:
            with transaction.atomic():
                reservation = InventoryReservation.objects.select_for_update().select_related('product').get(
                    product_id=request.product_id,
                    order_id=request.order_id,
                )
                product = Product.objects.select_for_update().get(id=request.product_id)
                if reservation.status == 'released':
                    return product_pb2.ReleaseStockResponse(
                        released=True,
                        remaining_quantity=product.inventory_count,
                    )
                product.inventory_count += reservation.quantity
                product.save(update_fields=['inventory_count', 'updated_at'])
                reservation.status = 'released'
                reservation.released_at = timezone.now()
                reservation.save(update_fields=['status', 'released_at'])
                return product_pb2.ReleaseStockResponse(
                    released=True,
                    remaining_quantity=product.inventory_count,
                )
        except InventoryReservation.DoesNotExist:
            return product_pb2.ReleaseStockResponse(
                released=False,
                error_message='Reservation not found',
            )
        except Exception:
            logger.exception('Error releasing stock for product %s', request.product_id)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('Internal server error')
            return product_pb2.ReleaseStockResponse(released=False, error_message='Internal server error')


def serve():
    """
    Start the gRPC server.
    
    Educational Note: This server runs alongside Django HTTP server.
    - HTTP: For frontend communication (port 8000)
    - gRPC: For inter-service communication (port 50052)
    """
    
    port = os.getenv('GRPC_PORT', '50052')
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Register our service implementation
    product_pb2_grpc.add_ProductServiceServicer_to_server(
        ProductServiceServicer(), server
    )
    
    # Use TLS in production. Development may explicitly opt into plaintext.
    tls_enabled = os.getenv('GRPC_TLS_ENABLED', 'false').lower() in {'1', 'true', 'yes', 'on'}
    if tls_enabled:
        cert_path = os.getenv('GRPC_CERT_PATH')
        key_path = os.getenv('GRPC_KEY_PATH')
        ca_path = os.getenv('GRPC_CA_PATH')
        if not all((cert_path, key_path, ca_path)):
            raise RuntimeError('GRPC_CERT_PATH, GRPC_KEY_PATH, and GRPC_CA_PATH are required for TLS')
        with open(cert_path, 'rb') as cert_file, open(key_path, 'rb') as key_file, open(ca_path, 'rb') as ca_file:
            credentials = grpc.ssl_server_credentials(
                [(key_file.read(), cert_file.read())],
                root_certificates=ca_file.read(),
                require_client_auth=True,
            )
        server.add_secure_port(f'[::]:{port}', credentials)
    else:
        server.add_insecure_port(f'[::]:{port}')
    
    # Start server
    server.start()
    
    logger.info(f"✓ gRPC server started on port {port}")
    logger.info("  Service: ProductService")
    logger.info("  Methods: GetProductInfo, CheckAvailability")
    logger.info("  Protocol: gRPC (HTTP/2 + Protocol Buffers)")
    logger.info("")
    logger.info("Educational Note:")
    logger.info("  - This server handles inter-service communication")
    logger.info("  - OrderService calls these methods to validate products")
    logger.info("  - 7-10x faster than REST (binary vs JSON)")
    logger.info("  - Type-safe (Protocol Buffers)")
    
    try:
        # Keep server running
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")
        server.stop(0)


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    serve()
