# apps/ventes_clients/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.db.models import Sum
from datetime import date, timedelta
from .models import (
    Client, Vente, LigneVente, Paiement, Facture,
    Avoir, Taxe, Remise, PointDeVente, SessionCaisse, MouvementCaisse
)
from produits_stocks.models import Product, Lot, Stock, StockMovement
from produits_stocks.serializers import ProductListSerializer, LotListSerializer


# ==================== CLIENT ====================
class ClientSerializer(serializers.ModelSerializer):
    full_address = serializers.ReadOnlyField()
    total_purchases_display = serializers.SerializerMethodField()
    credit_limit_display = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'code', 'name', 'commercial_name', 'type',
            'contact_person', 'phone', 'mobile', 'email', 'website',
            'address', 'city', 'country', 'postal_code',
            'tax_id', 'registration_number',
            'payment_terms', 'credit_limit', 'credit_limit_display',
            'current_balance', 'rating', 'total_purchases',
            'total_purchases_display', 'total_orders',
            'statut', 'is_favorite', 'notes',
            'created_at', 'updated_at', 'created_by', 'full_address'
        ]
        read_only_fields = ['id', 'created_at',
                            'updated_at', 'total_purchases', 'total_orders']

    def get_total_purchases_display(self, obj):
        return f"{obj.total_purchases:,.0f} FCFA" if obj.total_purchases else "0 FCFA"

    def get_credit_limit_display(self, obj):
        return f"{obj.credit_limit:,.0f} FCFA" if obj.credit_limit else "0 FCFA"

    def validate_code(self, value):
        if Client.objects.exclude(id=self.instance.id if self.instance else None).filter(code=value).exists():
            raise serializers.ValidationError("Ce code client existe déjà")
        return value


class ClientListSerializer(serializers.ModelSerializer):
    """Serializer léger pour la liste des clients"""
    total_purchases_display = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'code', 'name', 'commercial_name', 'type',
            'phone', 'email', 'city', 'statut', 'is_favorite',
            'total_purchases', 'total_purchases_display', 'rating'
        ]

    def get_total_purchases_display(self, obj):
        return f"{obj.total_purchases:,.0f} FCFA" if obj.total_purchases else "0 FCFA"


# ==================== VENTE ====================
class LigneVenteSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.code', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)

    class Meta:
        model = LigneVente
        fields = [
            'id', 'product', 'product_name', 'product_code',
            'lot', 'lot_number', 'quantity', 'unit_price',
            'discount', 'tax_rate', 'total', 'notes'
        ]
        read_only_fields = ['id', 'total']


class LigneVenteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneVente
        fields = ['product', 'lot', 'quantity',
                  'unit_price', 'discount', 'tax_rate', 'notes']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La quantité doit être supérieure à 0")
        return value

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le prix unitaire doit être supérieur à 0")
        return value


class VenteListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(
        source='get_payment_status_display', read_only=True)
    total_display = serializers.SerializerMethodField()

    class Meta:
        model = Vente
        fields = [
            'id', 'invoice_number', 'order_number', 'client', 'client_name',
            'sale_date', 'total', 'total_display', 'status', 'status_display',
            'payment_status', 'payment_status_display', 'amount_paid', 'amount_due',
            'created_by'
        ]
        read_only_fields = ['id', 'sale_date', 'invoice_number']

    def get_total_display(self, obj):
        return f"{obj.total:,.0f} FCFA" if obj.total else "0 FCFA"


class VenteDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    client_email = serializers.CharField(source='client.email', read_only=True)
    client_address = serializers.CharField(
        source='client.address', read_only=True)
    lines = LigneVenteSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(
        source='get_payment_status_display', read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True)
    total_display = serializers.SerializerMethodField()

    # QR Code fields
    qr_code = serializers.ImageField(read_only=True)
    qr_code_data = serializers.CharField(read_only=True)
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = Vente
        fields = [
            'id', 'invoice_number', 'order_number', 'client', 'client_name',
            'client_phone', 'client_email', 'client_address',
            'sale_date', 'delivery_date', 'payment_due_date',
            'subtotal', 'discount_type', 'discount_value', 'discount_amount',
            'tax_rate', 'tax_amount', 'shipping_fee', 'total', 'total_display',
            'payment_method', 'payment_status', 'payment_status_display',
            'amount_paid', 'amount_due', 'delivery_method', 'delivery_address',
            'delivery_status', 'tracking_number', 'status', 'status_display',
            'notes', 'internal_notes', 'lines', 'payments',
            'created_at', 'updated_at', 'created_by', 'created_by_name',
            'qr_code', 'qr_code_data', 'qr_code_url'
        ]
        read_only_fields = [
            'id', 'sale_date', 'invoice_number', 'qr_code', 'qr_code_data'
        ]

    def get_total_display(self, obj):
        return f"{obj.total:,.0f} FCFA" if obj.total else "0 FCFA"

    def get_qr_code_url(self, obj):
        if obj.qr_code:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.qr_code.url)
            return obj.qr_code.url
        return None

    def get_payments(self, obj):
        from .serializers import PaiementSerializer
        payments = obj.payments.all()
        return PaiementSerializer(payments, many=True).data


class VenteCreateSerializer(serializers.ModelSerializer):
    lines = LigneVenteCreateSerializer(many=True)

    class Meta:
        model = Vente
        fields = [
            'client', 'delivery_date', 'payment_due_date',
            'discount_type', 'discount_value', 'tax_rate', 'shipping_fee',
            'payment_method', 'delivery_method', 'delivery_address',
            'notes', 'internal_notes', 'lines'
        ]

    def validate_payment_due_date(self, value):
        if value < date.today():
            raise serializers.ValidationError(
                "La date d'échéance ne peut pas être dans le passé")
        return value

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        client = validated_data.get('client')

        # Générer le numéro de facture
        last_vente = Vente.objects.order_by('-id').first()
        if last_vente and last_vente.invoice_number:
            try:
                num = int(last_vente.invoice_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        invoice_number = f"INV-{date.today().year}-{num:04d}"

        # Créer la vente
        vente = Vente.objects.create(
            invoice_number=invoice_number,
            client_name=client.name if client else '',
            client_phone=client.phone if client else '',
            client_email=client.email if client else '',
            client_address=client.address if client else '',
            **validated_data
        )

        # Créer les lignes
        for line_data in lines_data:
            LigneVente.objects.create(sale=vente, **line_data)

        vente.calculate_totals()
        vente.generate_qr_code()
        vente.save()

        return vente


class VenteUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vente
        fields = [
            'delivery_date', 'payment_due_date', 'discount_type',
            'discount_value', 'tax_rate', 'shipping_fee',
            'payment_method', 'delivery_method', 'delivery_address',
            'notes', 'internal_notes', 'tracking_number'
        ]

    @transaction.atomic
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        instance.calculate_totals()
        instance.generate_qr_code()
        instance.save()
        return instance


class VenteStatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_status(self, value):
        allowed = ['draft', 'confirmed', 'paid',
                   'delivered', 'cancelled', 'returned']
        if value not in allowed:
            raise serializers.ValidationError(
                f"Statut invalide. Choisir parmi: {', '.join(allowed)}")
        return value


# ==================== PAIEMENT ====================
class PaiementSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(
        source='get_method_display', read_only=True)
    received_by_name = serializers.CharField(
        source='received_by.full_name', read_only=True)

    class Meta:
        model = Paiement
        fields = [
            'id', 'sale', 'amount', 'method', 'method_display',
            'reference', 'payment_date', 'received_by', 'received_by_name',
            'notes'
        ]
        read_only_fields = ['id', 'payment_date']


class PaiementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paiement
        fields = ['sale', 'amount', 'method', 'reference', 'notes']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le montant doit être supérieur à 0")
        return value


# ==================== FACTURE ====================
class FactureSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    sale_number = serializers.CharField(
        source='sale.invoice_number', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    remaining_amount = serializers.ReadOnlyField()

    # QR Code fields
    qr_code = serializers.ImageField(read_only=True)
    qr_code_data = serializers.CharField(read_only=True)
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            'id', 'invoice_number', 'sale', 'sale_number', 'client', 'client_name',
            'invoice_date', 'due_date', 'subtotal', 'tax_amount', 'total',
            'amount_paid', 'remaining_amount', 'status', 'status_display',
            'pdf_file', 'notes', 'qr_code', 'qr_code_data', 'qr_code_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_date', 'qr_code', 'qr_code_data']

    def get_qr_code_url(self, obj):
        if obj.qr_code:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.qr_code.url)
            return obj.qr_code.url
        return None


class FactureCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facture
        fields = ['sale', 'due_date', 'notes']

    def validate(self, data):
        sale = data.get('sale')
        if sale and sale.status in ['cancelled']:
            raise serializers.ValidationError(
                "Cette vente ne peut pas être facturée")
        return data

    @transaction.atomic
    def create(self, validated_data):
        sale = validated_data.get('sale')
        client = sale.client

        # Générer le numéro de facture
        last_facture = Facture.objects.order_by('-id').first()
        if last_facture and last_facture.invoice_number:
            try:
                num = int(last_facture.invoice_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        invoice_number = f"FAC-{date.today().year}-{num:04d}"

        facture = Facture.objects.create(
            invoice_number=invoice_number,
            client=client,
            subtotal=sale.subtotal,
            tax_amount=sale.tax_amount,
            total=sale.total,
            **validated_data
        )

        facture.generate_qr_code()
        facture.save()

        return facture


# ==================== AVOIR ====================
class AvoirSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    sale_number = serializers.CharField(
        source='sale.invoice_number', read_only=True)
    type_display = serializers.CharField(
        source='get_type_display', read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True)

    class Meta:
        model = Avoir
        fields = [
            'id', 'avoir_number', 'sale', 'sale_number', 'client', 'client_name',
            'type', 'type_display', 'amount', 'reason', 'date',
            'notes', 'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'date', 'avoir_number']


class AvoirCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Avoir
        fields = ['sale', 'client', 'type', 'amount', 'reason', 'notes']

    @transaction.atomic
    def create(self, validated_data):
        # Générer le numéro d'avoir
        last_avoir = Avoir.objects.order_by('-id').first()
        if last_avoir and last_avoir.avoir_number:
            try:
                num = int(last_avoir.avoir_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        avoir_number = f"AV-{date.today().year}-{num:04d}"

        avoir = Avoir.objects.create(
            avoir_number=avoir_number,
            **validated_data
        )

        return avoir


# ==================== TAXE ====================
class TaxeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Taxe
        fields = ['id', 'name', 'rate', 'is_default', 'is_active']
        read_only_fields = ['id']


# ==================== REMISE ====================
class RemiseSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display', read_only=True)
    clients_count = serializers.SerializerMethodField()

    class Meta:
        model = Remise
        fields = [
            'id', 'name', 'type', 'type_display', 'value',
            'min_purchase', 'start_date', 'end_date',
            'is_active', 'clients', 'clients_count', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_clients_count(self, obj):
        return obj.clients.count()


# ==================== POINT DE VENTE ====================
class PointDeVenteSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(
        source='warehouse.name', read_only=True)

    class Meta:
        model = PointDeVente
        fields = ['id', 'name', 'code', 'warehouse',
                  'warehouse_name', 'is_active']
        read_only_fields = ['id']


# ==================== SESSION CAISSE ====================
class SessionCaisseSerializer(serializers.ModelSerializer):
    point_de_vente_name = serializers.CharField(
        source='point_de_vente.name', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    movements = serializers.SerializerMethodField()

    class Meta:
        model = SessionCaisse
        fields = [
            'id', 'point_de_vente', 'point_de_vente_name',
            'user', 'user_name', 'opening_date', 'closing_date',
            'opening_balance', 'closing_balance', 'expected_balance',
            'difference', 'status', 'status_display', 'notes', 'movements'
        ]
        read_only_fields = ['id', 'opening_date', 'closing_date']

    def get_movements(self, obj):
        from .serializers import MouvementCaisseSerializer
        movements = obj.movements.all()
        return MouvementCaisseSerializer(movements, many=True).data


class SessionCaisseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionCaisse
        fields = ['point_de_vente', 'opening_balance', 'notes']


# ==================== MOUVEMENT CAISSE ====================
class MouvementCaisseSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source='get_type_display', read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True)

    class Meta:
        model = MouvementCaisse
        fields = [
            'id', 'session', 'type', 'type_display', 'amount',
            'description', 'reference', 'created_at', 'created_by',
            'created_by_name'
        ]
        read_only_fields = ['id', 'created_at']


class MouvementCaisseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MouvementCaisse
        fields = ['session', 'type', 'amount', 'description', 'reference']

    def validate(self, data):
        session = data.get('session')
        if session and session.status != 'open':
            raise serializers.ValidationError(
                "La session de caisse est fermée")
        return data
