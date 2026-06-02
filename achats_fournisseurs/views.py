# apps/achats_fournisseurs/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import date, timedelta
from .models import (
    Supplier, SupplierContact, SupplierProduct, PurchaseOrder,
    PurchaseOrderLine, Receipt, ReceiptLine, PurchaseReturn,
    PurchaseReturnLine, SupplierInvoice
)
from .serializers import (
    SupplierListSerializer, SupplierDetailSerializer, SupplierWriteSerializer,
    SupplierContactSerializer, SupplierProductSerializer,
    PurchaseOrderListSerializer, PurchaseOrderDetailSerializer,
    PurchaseOrderCreateSerializer, PurchaseOrderUpdateSerializer,
    PurchaseOrderApproveSerializer, ReceiptListSerializer,
    ReceiptDetailSerializer, ReceiptCreateSerializer,
    PurchaseReturnSerializer, PurchaseReturnCreateSerializer,
    SupplierInvoiceSerializer, SupplierInvoiceCreateSerializer,
    SupplierInvoicePaymentSerializer
)
from users.permissions import IsAdmin, IsGestionnaire, IsMagasinier


# ==================== SUPPLIER VIEWSET ====================
class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsGestionnaire]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return SupplierWriteSerializer
        return SupplierDetailSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search)
            )
        
        type_filter = self.request.query_params.get('type')
        if type_filter:
            queryset = queryset.filter(type=type_filter)
        
        is_active = self.request.query_params.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        
        is_preferred = self.request.query_params.get('is_preferred')
        if is_preferred == 'true':
            queryset = queryset.filter(is_preferred=True)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def contacts(self, request, pk=None):
        supplier = self.get_object()
        contacts = supplier.contacts.all()
        serializer = SupplierContactSerializer(contacts, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        supplier = self.get_object()
        products = supplier.products.filter(is_active=True)
        serializer = SupplierProductSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def purchase_orders(self, request, pk=None):
        supplier = self.get_object()
        orders = supplier.purchase_orders.all().order_by('-order_date')
        serializer = PurchaseOrderListSerializer(orders, many=True)
        return Response(serializer.data)


# ==================== PURCHASE ORDER VIEWSET ====================
class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsGestionnaire]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseOrderListSerializer
        elif self.action == 'create':
            return PurchaseOrderCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PurchaseOrderUpdateSerializer
        return PurchaseOrderDetailSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(po_number__icontains=search) |
                Q(supplier__name__icontains=search)
            )
        
        supplier = self.request.query_params.get('supplier')
        if supplier:
            queryset = queryset.filter(supplier_id=supplier)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(order_date__date__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(order_date__date__lte=date_to)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        purchase_order = self.get_object()
        serializer = PurchaseOrderApproveSerializer(data=request.data)
        
        if serializer.is_valid():
            if serializer.validated_data['approved']:
                purchase_order.status = 'confirmed'
                purchase_order.approved_by = request.user
                purchase_order.approved_at = timezone.now()
            else:
                purchase_order.status = 'cancelled'
            purchase_order.save()
            return Response({'status': purchase_order.status})
        
        return Response(serializer.errors, status=400)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        purchase_order = self.get_object()
        
        if purchase_order.status not in ['draft', 'sent']:
            return Response({"error": "Cette commande ne peut pas être annulée"}, status=400)
        
        purchase_order.status = 'cancelled'
        purchase_order.save()
        return Response({'status': purchase_order.status})
    
    @action(detail=True, methods=['get'])
    def receipts(self, request, pk=None):
        purchase_order = self.get_object()
        receipts = purchase_order.receipts.all()
        serializer = ReceiptListSerializer(receipts, many=True)
        return Response(serializer.data)


# ==================== RECEIPT VIEWSET ====================
class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = Receipt.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsMagasinier]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ReceiptListSerializer
        elif self.action == 'create':
            return ReceiptCreateSerializer
        return ReceiptDetailSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        purchase_order = self.request.query_params.get('purchase_order')
        if purchase_order:
            queryset = queryset.filter(purchase_order_id=purchase_order)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        receipt = self.get_object()
        
        if receipt.status != 'in_progress':
            return Response({"error": "Cette réception ne peut pas être annulée"}, status=400)
        
        receipt.status = 'cancelled'
        receipt.save()
        return Response({'status': receipt.status})


# ==================== PURCHASE RETURN VIEWSET ====================
class PurchaseReturnViewSet(viewsets.ModelViewSet):
    queryset = PurchaseReturn.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsGestionnaire]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PurchaseReturnCreateSerializer
        return PurchaseReturnSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        purchase_order = self.request.query_params.get('purchase_order')
        if purchase_order:
            queryset = queryset.filter(purchase_order_id=purchase_order)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        purchase_return = self.get_object()
        purchase_return.status = 'approved'
        purchase_return.save()
        return Response({'status': purchase_return.status})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        purchase_return = self.get_object()
        purchase_return.status = 'rejected'
        purchase_return.save()
        return Response({'status': purchase_return.status})


# ==================== SUPPLIER INVOICE VIEWSET ====================
class SupplierInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SupplierInvoice.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsGestionnaire]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return SupplierInvoiceCreateSerializer
        return SupplierInvoiceSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        purchase_order = self.request.query_params.get('purchase_order')
        if purchase_order:
            queryset = queryset.filter(purchase_order_id=purchase_order)
        
        supplier = self.request.query_params.get('supplier')
        if supplier:
            queryset = queryset.filter(supplier_id=supplier)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(supplier=serializer.validated_data['purchase_order'].supplier)
    
    @action(detail=True, methods=['post'])
    def register_payment(self, request, pk=None):
        invoice = self.get_object()
        serializer = SupplierInvoicePaymentSerializer(data=request.data)
        
        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            
            if amount > invoice.remaining_amount:
                return Response({"error": "Le montant dépasse le solde restant"}, status=400)
            
            invoice.amount_paid += amount
            invoice.payment_date = serializer.validated_data['payment_date']
            invoice.payment_reference = serializer.validated_data.get('payment_reference', '')
            
            if invoice.amount_paid >= invoice.total_amount:
                invoice.status = 'paid'
            else:
                invoice.status = 'partial'
            
            invoice.save()
            
            return Response({
                'status': invoice.status,
                'amount_paid': invoice.amount_paid,
                'remaining_amount': invoice.remaining_amount
            })
        
        return Response(serializer.errors, status=400)