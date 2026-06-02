# apps/achats_fournisseurs/serializers.py
from rest_framework import serializers
from django.db import transaction
from datetime import date
from .models import (
    Supplier, SupplierContact, SupplierProduct, PurchaseOrder,
    PurchaseOrderLine, Receipt, ReceiptLine, PurchaseReturn,
    PurchaseReturnLine, SupplierInvoice
)
from produits_stocks.models import Product, Lot, Stock, StockMovement
from produits_stocks.serializers import ProductListSerializer, LotListSerializer


# ==================== SUPPLIER ====================
class SupplierContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierContact
        fields = [
            'id', 'name', 'position', 'phone', 'mobile', 'email',
            'is_primary', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SupplierProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.code', read_only=True)
    product_unit = serializers.CharField(source='product.unit.symbol', read_only=True)
    
    class Meta:
        model = SupplierProduct
        fields = [
            'id', 'product', 'product_name', 'product_code', 'product_unit',
            'supplier_sku', 'purchase_price', 'lead_time', 'minimum_order',
            'is_active', 'notes', 'last_updated'
        ]
        read_only_fields = ['id', 'last_updated']


class SupplierListSerializer(serializers.ModelSerializer):
    total_purchases_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'code', 'name', 'commercial_name', 'type', 'phone',
            'email', 'city', 'is_active', 'is_preferred', 'rating',
            'total_purchases', 'total_purchases_display'
        ]
        read_only_fields = ['id', 'total_purchases', 'total_orders']
    
    def get_total_purchases_display(self, obj):
        return f"{obj.total_purchases:,.0f} FCFA" if obj.total_purchases else "0 FCFA"


class SupplierDetailSerializer(serializers.ModelSerializer):
    contacts = SupplierContactSerializer(many=True, read_only=True)
    products = SupplierProductSerializer(many=True, read_only=True)
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'code', 'name', 'commercial_name', 'type', 'contact_person',
            'phone', 'mobile', 'email', 'website', 'address', 'city',
            'country', 'postal_code', 'tax_id', 'registration_number',
            'payment_terms', 'delivery_lead_time', 'minimum_order',
            'rating', 'total_purchases', 'total_orders', 'on_time_delivery_rate',
            'is_active', 'is_preferred', 'notes', 'contacts', 'products',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_purchases', 'total_orders']


class SupplierWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            'code', 'name', 'commercial_name', 'type', 'contact_person',
            'phone', 'mobile', 'email', 'website', 'address', 'city',
            'country', 'postal_code', 'tax_id', 'registration_number',
            'payment_terms', 'delivery_lead_time', 'minimum_order',
            'is_active', 'is_preferred', 'notes'
        ]
    
    def validate_code(self, value):
        if Supplier.objects.exclude(id=self.instance.id if self.instance else None).filter(code=value).exists():
            raise serializers.ValidationError("Ce code fournisseur existe déjà")
        return value


# ==================== PURCHASE ORDER ====================
class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.code', read_only=True)
    quantity_remaining = serializers.ReadOnlyField()
    
    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'product', 'product_name', 'product_code', 'quantity',
            'quantity_received', 'quantity_remaining', 'unit_price',
            'discount', 'tax_rate', 'total', 'notes'
        ]
        read_only_fields = ['id', 'quantity_received', 'total']


class PurchaseOrderLineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = ['product', 'quantity', 'unit_price', 'discount', 'tax_rate', 'notes']
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité doit être supérieure à 0")
        return value
    
    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le prix unitaire doit être supérieur à 0")
        return value


class PurchaseOrderListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_code = serializers.CharField(source='supplier.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier', 'supplier_name', 'supplier_code',
            'order_date', 'expected_delivery_date', 'actual_delivery_date',
            'total', 'status', 'status_display', 'created_by'
        ]
        read_only_fields = ['id', 'order_date', 'po_number']


class PurchaseOrderDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_code = serializers.CharField(source='supplier.code', read_only=True)
    supplier_address = serializers.CharField(source='supplier.address', read_only=True)
    supplier_phone = serializers.CharField(source='supplier.phone', read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier_reference', 'supplier', 'supplier_name',
            'supplier_code', 'supplier_address', 'supplier_phone', 'order_date',
            'expected_delivery_date', 'actual_delivery_date', 'subtotal',
            'discount_type', 'discount_value', 'discount_amount', 'tax_rate',
            'tax_amount', 'shipping_cost', 'total', 'status', 'status_display',
            'notes', 'internal_notes', 'shipping_address', 'tracking_number',
            'lines', 'created_at', 'updated_at', 'created_by', 'created_by_name',
            'approved_by', 'approved_by_name', 'approved_at'
        ]
        read_only_fields = ['id', 'order_date', 'po_number']


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineCreateSerializer(many=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'supplier', 'supplier_reference', 'expected_delivery_date',
            'discount_type', 'discount_value', 'tax_rate', 'shipping_cost',
            'notes', 'internal_notes', 'shipping_address', 'lines'
        ]
    
    def validate_expected_delivery_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("La date de livraison prévue ne peut pas être dans le passé")
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        
        last_po = PurchaseOrder.objects.order_by('-id').first()
        if last_po and last_po.po_number:
            try:
                num = int(last_po.po_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        po_number = f"PO-{date.today().year}-{num:04d}"
        
        purchase_order = PurchaseOrder.objects.create(
            po_number=po_number,
            **validated_data
        )
        
        for line_data in lines_data:
            PurchaseOrderLine.objects.create(
                purchase_order=purchase_order,
                **line_data
            )
        
        purchase_order.calculate_totals()
        return purchase_order


class PurchaseOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = [
            'supplier_reference', 'expected_delivery_date', 'discount_type',
            'discount_value', 'tax_rate', 'shipping_cost', 'notes',
            'internal_notes', 'shipping_address', 'tracking_number'
        ]
    
    @transaction.atomic
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        instance.calculate_totals()
        return instance


class PurchaseOrderApproveSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True)


# ==================== RECEIPT ====================
class ReceiptLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.code', read_only=True)
    po_line_quantity = serializers.IntegerField(source='po_line.quantity', read_only=True)
    
    class Meta:
        model = ReceiptLine
        fields = [
            'id', 'product', 'product_name', 'product_code', 'po_line',
            'quantity_ordered', 'quantity_received', 'quantity_damaged',
            'lot', 'lot_number', 'expiry_date', 'manufacturing_date',
            'is_quality_checked', 'quality_status', 'quality_notes', 'notes'
        ]
        read_only_fields = ['id', 'po_line', 'quantity_ordered']


class ReceiptLineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptLine
        fields = [
            'po_line', 'quantity_received', 'quantity_damaged', 'lot_number',
            'expiry_date', 'manufacturing_date', 'quality_status', 'quality_notes', 'notes'
        ]
    
    def validate_quantity_received(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité reçue doit être supérieure à 0")
        return value


class ReceiptListSerializer(serializers.ModelSerializer):
    po_number = serializers.CharField(source='purchase_order.po_number', read_only=True)
    supplier_name = serializers.CharField(source='purchase_order.supplier.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'po_number', 'supplier_name', 'warehouse',
            'warehouse_name', 'receipt_date', 'expected_date', 'status',
            'status_display', 'created_by'
        ]
        read_only_fields = ['id', 'receipt_number', 'receipt_date']


class ReceiptDetailSerializer(serializers.ModelSerializer):
    po_number = serializers.CharField(source='purchase_order.po_number', read_only=True)
    supplier_name = serializers.CharField(source='purchase_order.supplier.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    lines = ReceiptLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    
    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'purchase_order', 'po_number', 'supplier_name',
            'receipt_date', 'expected_date', 'warehouse', 'warehouse_name',
            'status', 'status_display', 'notes', 'delivery_note', 'invoice_number',
            'lines', 'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'receipt_number', 'receipt_date']


class ReceiptCreateSerializer(serializers.ModelSerializer):
    lines = ReceiptLineCreateSerializer(many=True)
    
    class Meta:
        model = Receipt
        fields = ['purchase_order', 'expected_date', 'warehouse', 'delivery_note', 'invoice_number', 'notes', 'lines']
    
    def validate(self, data):
        purchase_order = data.get('purchase_order')
        if purchase_order and purchase_order.status in ['cancelled', 'received']:
            raise serializers.ValidationError("Cette commande ne peut plus être réceptionnée")
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        purchase_order = validated_data.get('purchase_order')
        
        last_receipt = Receipt.objects.order_by('-id').first()
        if last_receipt and last_receipt.receipt_number:
            try:
                num = int(last_receipt.receipt_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        receipt_number = f"REC-{date.today().year}-{num:04d}"
        
        receipt = Receipt.objects.create(
            receipt_number=receipt_number,
            status='in_progress',
            **validated_data
        )
        
        for line_data in lines_data:
            po_line = line_data.get('po_line')
            quantity_received = line_data.get('quantity_received')
            
            if quantity_received > po_line.quantity_remaining:
                raise serializers.ValidationError(
                    f"Quantité reçue ({quantity_received}) dépasse la quantité restante ({po_line.quantity_remaining})"
                )
            
            lot = None
            if line_data.get('lot_number'):
                lot, created = Lot.objects.get_or_create(
                    lot_number=line_data['lot_number'],
                    defaults={
                        'product': po_line.product,
                        'warehouse': receipt.warehouse,
                        'initial_quantity': 0,
                        'current_quantity': 0,
                        'expiry_date': line_data.get('expiry_date'),
                        'manufacturing_date': line_data.get('manufacturing_date'),
                        'purchase_price': po_line.unit_price,
                        'selling_price': po_line.product.selling_price,
                        'created_by': self.context['request'].user
                    }
                )
                
                lot.initial_quantity += quantity_received
                lot.current_quantity += quantity_received
                lot.save()
            
            ReceiptLine.objects.create(
                receipt=receipt,
                product=po_line.product,
                quantity_ordered=po_line.quantity,
                quantity_received=quantity_received,
                lot=lot,
                **line_data
            )
            
            po_line.quantity_received += quantity_received
            po_line.save()
            
            if lot:
                StockMovement.objects.create(
                    product=po_line.product,
                    lot=lot,
                    to_warehouse=receipt.warehouse,
                    movement_type='purchase_in',
                    quantity=quantity_received,
                    reference_type='purchase_order',
                    reference_id=purchase_order.id,
                    reference_number=purchase_order.po_number,
                    reason=f"Réception commande {purchase_order.po_number}",
                    created_by=self.context['request'].user
                )
        
        if purchase_order.lines.filter(quantity_remaining__gt=0).exists():
            purchase_order.status = 'partial'
        else:
            purchase_order.status = 'received'
        purchase_order.save()
        
        receipt.status = 'completed'
        receipt.save()
        
        return receipt


# ==================== PURCHASE RETURN ====================
class PurchaseReturnLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.code', read_only=True)
    
    class Meta:
        model = PurchaseReturnLine
        fields = ['id', 'receipt_line', 'product', 'product_name', 'product_code', 'quantity', 'unit_price', 'total']
        read_only_fields = ['total']


class PurchaseReturnSerializer(serializers.ModelSerializer):
    po_number = serializers.CharField(source='purchase_order.po_number', read_only=True)
    supplier_name = serializers.CharField(source='purchase_order.supplier.name', read_only=True)
    supplier_code = serializers.CharField(source='purchase_order.supplier.code', read_only=True)
    receipt_number = serializers.CharField(source='receipt.receipt_number', read_only=True)
    lines = PurchaseReturnLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    
    class Meta:
        model = PurchaseReturn
        fields = [
            'id', 'return_number', 'purchase_order', 'po_number', 'supplier_name',
            'supplier_code', 'receipt', 'receipt_number', 'return_date', 'reason',
            'reason_display', 'status', 'status_display', 'notes', 'lines',
            'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'return_number', 'return_date', 'created_at']


class PurchaseReturnCreateSerializer(serializers.ModelSerializer):
    lines = serializers.ListField(child=serializers.DictField(), write_only=True)
    
    class Meta:
        model = PurchaseReturn
        fields = ['purchase_order', 'receipt', 'reason', 'notes', 'lines']
    
    def validate(self, data):
        purchase_order = data.get('purchase_order')
        receipt = data.get('receipt')
        
        if receipt and receipt.purchase_order != purchase_order:
            raise serializers.ValidationError("La réception ne correspond pas à la commande")
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        
        last_return = PurchaseReturn.objects.order_by('-id').first()
        if last_return and last_return.return_number:
            try:
                num = int(last_return.return_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        return_number = f"RET-{date.today().year}-{num:04d}"
        
        purchase_return = PurchaseReturn.objects.create(
            return_number=return_number,
            **validated_data
        )
        
        for line_data in lines_data:
            receipt_line = line_data.get('receipt_line')
            quantity = line_data.get('quantity')
            product = receipt_line.product
            
            PurchaseReturnLine.objects.create(
                purchase_return=purchase_return,
                receipt_line=receipt_line,
                product=product,
                quantity=quantity,
                unit_price=receipt_line.po_line.unit_price
            )
            
            if receipt_line.lot:
                receipt_line.lot.current_quantity -= quantity
                receipt_line.lot.save()
                
                StockMovement.objects.create(
                    product=product,
                    lot=receipt_line.lot,
                    from_warehouse=receipt_line.lot.warehouse,
                    movement_type='return_out',
                    quantity=quantity,
                    reference_type='purchase_return',
                    reference_id=purchase_return.id,
                    reference_number=return_number,
                    reason=f"Retour fournisseur - {purchase_return.get_reason_display()}",
                    created_by=self.context['request'].user
                )
            
            receipt_line.quantity_received -= quantity
            receipt_line.save()
        
        return purchase_return


# ==================== SUPPLIER INVOICE ====================
class SupplierInvoiceSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    po_number = serializers.CharField(source='purchase_order.po_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    remaining_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = SupplierInvoice
        fields = [
            'id', 'invoice_number', 'purchase_order', 'po_number', 'supplier',
            'supplier_name', 'invoice_date', 'due_date', 'amount', 'tax_amount',
            'total_amount', 'amount_paid', 'remaining_amount', 'status',
            'status_display', 'payment_date', 'payment_reference', 'notes'
        ]
        read_only_fields = ['id', 'amount_paid']


class SupplierInvoiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierInvoice
        fields = [
            'invoice_number', 'purchase_order', 'invoice_date', 'due_date',
            'amount', 'tax_amount', 'total_amount', 'notes'
        ]
    
    def validate_invoice_number(self, value):
        if SupplierInvoice.objects.filter(invoice_number=value).exists():
            raise serializers.ValidationError("Ce numéro de facture existe déjà")
        return value


class SupplierInvoicePaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_date = serializers.DateField()
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à 0")
        return value