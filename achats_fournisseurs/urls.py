# apps/achats_fournisseurs/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SupplierViewSet, PurchaseOrderViewSet, ReceiptViewSet,
    PurchaseReturnViewSet, SupplierInvoiceViewSet
)

router = DefaultRouter()
router.register('suppliers', SupplierViewSet, basename='suppliers')
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-orders')
router.register('receipts', ReceiptViewSet, basename='receipts')
router.register('purchase-returns', PurchaseReturnViewSet, basename='purchase-returns')
router.register('supplier-invoices', SupplierInvoiceViewSet, basename='supplier-invoices')

urlpatterns = [
    path('', include(router.urls)),
]