# apps/ventes_clients/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import date, timedelta
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from PIL import Image as PILImage
import json

from .models import (
    Client, Vente, LigneVente, Paiement, Facture,
    Avoir, Taxe, Remise, PointDeVente, SessionCaisse, MouvementCaisse
)
from .serializers import (
    ClientSerializer, ClientListSerializer,
    VenteListSerializer, VenteDetailSerializer,
    VenteCreateSerializer, VenteUpdateSerializer,
    VenteStatusUpdateSerializer,
    LigneVenteSerializer, LigneVenteCreateSerializer,
    PaiementSerializer, PaiementCreateSerializer,
    FactureSerializer, FactureCreateSerializer,
    AvoirSerializer, AvoirCreateSerializer,
    TaxeSerializer, RemiseSerializer,
    PointDeVenteSerializer, SessionCaisseSerializer,
    SessionCaisseCreateSerializer,
    MouvementCaisseSerializer, MouvementCaisseCreateSerializer
)
from users.permissions import IsAdmin, IsGestionnaire, IsCaissier
from produits_stocks.models import Stock, StockMovement


# ==================== CLIENT VIEWSET ====================
class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return ClientListSerializer
        return ClientSerializer

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

        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        is_favorite = self.request.query_params.get('is_favorite')
        if is_favorite == 'true':
            queryset = queryset.filter(is_favorite=True)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def sales(self, request, pk=None):
        client = self.get_object()
        sales = client.sales.all().order_by('-sale_date')
        serializer = VenteListSerializer(sales, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        client = self.get_object()
        sales = client.sales.all()

        stats = {
            'total_orders': sales.count(),
            'total_purchases': sales.aggregate(total=Sum('total'))['total'] or 0,
            'orders_by_status': {},
            'average_order_value': 0,
        }

        for status_choice in Vente.STATUS_CHOICES:
            status_code = status_choice[0]
            count = sales.filter(status=status_code).count()
            if count > 0:
                stats['orders_by_status'][status_code] = count

        if stats['total_orders'] > 0:
            stats['average_order_value'] = stats['total_purchases'] / \
                stats['total_orders']

        return Response(stats)


# ==================== VENTE VIEWSET ====================
class VenteViewSet(viewsets.ModelViewSet):
    queryset = Vente.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return VenteListSerializer
        elif self.action == 'create':
            return VenteCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return VenteUpdateSerializer
        return VenteDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        queryset = super().get_queryset()

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search) |
                Q(client__name__icontains=search) |
                Q(client_name__icontains=search)
            )

        client = self.request.query_params.get('client')
        if client:
            queryset = queryset.filter(client_id=client)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(sale_date__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(sale_date__date__lte=date_to)

        min_total = self.request.query_params.get('min_total')
        if min_total:
            queryset = queryset.filter(total__gte=min_total)

        max_total = self.request.query_params.get('max_total')
        if max_total:
            queryset = queryset.filter(total__lte=max_total)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        vente = self.get_object()
        serializer = VenteStatusUpdateSerializer(data=request.data)

        if serializer.is_valid():
            old_status = vente.status
            new_status = serializer.validated_data['status']

            vente.status = new_status
            vente.save()

            # Générer le QR Code
            vente.generate_qr_code()
            vente.save()

            return Response({
                'status': vente.status,
                'message': f'Statut changé de {old_status} à {new_status}'
            })

        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        vente = self.get_object()

        if vente.status in ['paid', 'delivered']:
            return Response(
                {"error": "Cette vente ne peut pas être annulée"},
                status=400
            )

        vente.status = 'cancelled'
        vente.save()
        vente.generate_qr_code()
        vente.save()

        return Response({
            'status': vente.status,
            'message': 'Vente annulée avec succès'
        })

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        vente = self.get_object()
        data = request.data.copy()
        data['sale'] = vente.id

        serializer = PaiementCreateSerializer(data=data)
        if serializer.is_valid():
            payment = serializer.save(received_by=request.user)
            return Response(PaiementSerializer(payment).data, status=201)

        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        vente = self.get_object()
        payments = vente.payments.all()
        serializer = PaiementSerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def generate_qr(self, request, pk=None):
        vente = self.get_object()

        if not vente.qr_code:
            vente.generate_qr_code()
            vente.save()

        if vente.qr_code:
            return Response({
                'qr_code_url': request.build_absolute_uri(vente.qr_code.url),
                'qr_code_data': vente.qr_code_data
            })

        return Response(
            {"error": "Impossible de générer le QR Code"},
            status=500
        )

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """Génère un PDF de la vente avec QR Code"""
        vente = self.get_object()

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Titre
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a237e'),
            alignment=TA_CENTER,
            spaceAfter=30
        )
        elements.append(Paragraph("FACTURE", title_style))

        # Informations
        info_style = ParagraphStyle(
            'Info',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6
        )

        elements.append(
            Paragraph(f"<b>N° Facture:</b> {vente.invoice_number}", info_style))
        elements.append(Paragraph(
            f"<b>Date:</b> {vente.sale_date.strftime('%d/%m/%Y %H:%M')}", info_style))
        elements.append(
            Paragraph(f"<b>Client:</b> {vente.client_name}", info_style))
        elements.append(
            Paragraph(f"<b>Statut:</b> {vente.get_status_display()}", info_style))
        elements.append(Spacer(1, 12))

        # QR Code
        if vente.qr_code:
            try:
                qr_path = vente.qr_code.path
                qr_img = PILImage.open(qr_path)
                qr_buffer = BytesIO()
                qr_img.save(qr_buffer, format='PNG')
                qr_buffer.seek(0)
                qr_width, qr_height = 80, 80
                from reportlab.platypus import Image
                qr_image = Image(qr_buffer, width=qr_width, height=qr_height)
                elements.append(qr_image)
                elements.append(Spacer(1, 12))
            except Exception as e:
                print(f"Erreur QR Code: {e}")

        # Tableau des produits
        data = [['Produit', 'Quantité', 'Prix unitaire', 'Remise', 'Total']]
        for line in vente.lines.all():
            data.append([
                line.product.name,
                str(line.quantity),
                f"{line.unit_price:,.0f} FCFA",
                f"{line.discount:,.0f} FCFA",
                f"{line.total:,.0f} FCFA"
            ])

        data.append(['', '', '', 'Sous-total', f"{vente.subtotal:,.0f} FCFA"])
        if vente.discount_amount > 0:
            data.append(
                ['', '', '', 'Remise', f"-{vente.discount_amount:,.0f} FCFA"])
        if vente.tax_amount > 0:
            data.append(['', '', '', 'TVA', f"{vente.tax_amount:,.0f} FCFA"])
        if vente.shipping_fee > 0:
            data.append(['', '', '', 'Frais livraison',
                        f"{vente.shipping_fee:,.0f} FCFA"])
        data.append(['', '', '', 'TOTAL', f"{vente.total:,.0f} FCFA"])

        table = Table(data, colWidths=[
                      2.5*inch, 0.8*inch, 1.2*inch, 0.8*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eaf6')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#1a237e')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -2), 1, colors.grey),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 20))

        # Notes
        if vente.notes:
            elements.append(Paragraph("<b>Notes:</b>", info_style))
            elements.append(Paragraph(vente.notes, info_style))

        # Pied de page
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        elements.append(Spacer(1, 30))
        elements.append(
            Paragraph("Document généré automatiquement", footer_style))
        elements.append(
            Paragraph(f"Date: {timezone.now().strftime('%d/%m/%Y %H:%M')}", footer_style))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="facture_{vente.invoice_number}.pdf"'
        return response


# ==================== PAIEMENT VIEWSET ====================
class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.all()
    serializer_class = PaiementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        sale_id = self.request.query_params.get('sale')
        if sale_id:
            queryset = queryset.filter(sale_id=sale_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)


# ==================== FACTURE VIEWSET ====================
class FactureViewSet(viewsets.ModelViewSet):
    queryset = Facture.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return FactureCreateSerializer
        return FactureSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        queryset = super().get_queryset()

        client = self.request.query_params.get('client')
        if client:
            queryset = queryset.filter(client_id=client)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        facture = self.get_object()
        amount = request.data.get('amount', 0)

        if amount <= 0:
            return Response({"error": "Le montant doit être supérieur à 0"}, status=400)

        if amount > facture.remaining_amount:
            return Response({"error": "Le montant dépasse le solde restant"}, status=400)

        facture.amount_paid += amount
        if facture.amount_paid >= facture.total:
            facture.status = 'paid'
        facture.save()

        return Response({
            'status': facture.status,
            'amount_paid': facture.amount_paid,
            'remaining_amount': facture.remaining_amount
        })

    @action(detail=True, methods=['get'])
    def generate_qr(self, request, pk=None):
        facture = self.get_object()

        if not facture.qr_code:
            facture.generate_qr_code()
            facture.save()

        if facture.qr_code:
            return Response({
                'qr_code_url': request.build_absolute_uri(facture.qr_code.url),
                'qr_code_data': facture.qr_code_data
            })

        return Response(
            {"error": "Impossible de générer le QR Code"},
            status=500
        )


# ==================== AVOIR VIEWSET ====================
class AvoirViewSet(viewsets.ModelViewSet):
    queryset = Avoir.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return AvoirCreateSerializer
        return AvoirSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()

        client = self.request.query_params.get('client')
        if client:
            queryset = queryset.filter(client_id=client)

        return queryset


# ==================== TAXE VIEWSET ====================
class TaxeViewSet(viewsets.ModelViewSet):
    queryset = Taxe.objects.all()
    serializer_class = TaxeSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


# ==================== REMISE VIEWSET ====================
class RemiseViewSet(viewsets.ModelViewSet):
    queryset = Remise.objects.all()
    serializer_class = RemiseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        is_active = self.request.query_params.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)

        return queryset


# ==================== POINT DE VENTE VIEWSET ====================
class PointDeVenteViewSet(viewsets.ModelViewSet):
    queryset = PointDeVente.objects.all()
    serializer_class = PointDeVenteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        is_active = self.request.query_params.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)

        return queryset


# ==================== SESSION CAISSE VIEWSET ====================
class SessionCaisseViewSet(viewsets.ModelViewSet):
    queryset = SessionCaisse.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return SessionCaisseCreateSerializer
        return SessionCaisseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        point_de_vente = self.request.query_params.get('point_de_vente')
        if point_de_vente:
            queryset = queryset.filter(point_de_vente_id=point_de_vente)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        session = self.get_object()

        if session.status != 'open':
            return Response({"error": "Cette session est déjà fermée"}, status=400)

        closing_balance = request.data.get('closing_balance', 0)

        session.closing_balance = closing_balance
        session.expected_balance = session.opening_balance + session.movements.filter(
            type__in=['sale', 'deposit']
        ).aggregate(total=Sum('amount'))['total'] or 0
        session.expected_balance -= session.movements.filter(
            type__in=['withdrawal', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or 0
        session.difference = closing_balance - session.expected_balance
        session.status = 'closed'
        session.closing_date = timezone.now()
        session.save()

        return Response({
            'status': session.status,
            'expected_balance': session.expected_balance,
            'closing_balance': session.closing_balance,
            'difference': session.difference
        })

    @action(detail=True, methods=['post'])
    def add_movement(self, request, pk=None):
        session = self.get_object()

        if session.status != 'open':
            return Response({"error": "La session est fermée"}, status=400)

        data = request.data.copy()
        data['session'] = session.id

        serializer = MouvementCaisseCreateSerializer(data=data)
        if serializer.is_valid():
            movement = serializer.save(created_by=request.user)
            return Response(MouvementCaisseSerializer(movement).data, status=201)

        return Response(serializer.errors, status=400)


# ==================== DASHBOARD STATS VIEWSET ====================
class SalesDashboardStatsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Statistiques résumées pour le dashboard des ventes"""
        today = date.today()
        start_of_month = today.replace(day=1)
        start_of_week = today - timedelta(days=today.weekday())

        total_sales = Vente.objects.count()
        sales_today = Vente.objects.filter(sale_date__date=today).count()
        sales_this_month = Vente.objects.filter(
            sale_date__date__gte=start_of_month).count()
        sales_this_week = Vente.objects.filter(
            sale_date__date__gte=start_of_week).count()

        total_amount = Vente.objects.aggregate(
            total=Sum('total'))['total'] or 0
        amount_today = Vente.objects.filter(sale_date__date=today).aggregate(
            total=Sum('total'))['total'] or 0
        amount_this_month = Vente.objects.filter(
            sale_date__date__gte=start_of_month).aggregate(total=Sum('total'))['total'] or 0

        pending_payments = Vente.objects.filter(
            payment_status__in=['pending', 'partial']).count()
        pending_amount = Vente.objects.filter(payment_status__in=[
                                              'pending', 'partial']).aggregate(total=Sum('amount_due'))['total'] or 0

        total_clients = Client.objects.filter(statut='actif').count()

        return Response({
            'sales': {
                'total': total_sales,
                'today': sales_today,
                'this_week': sales_this_week,
                'this_month': sales_this_month
            },
            'amounts': {
                'total': total_amount,
                'today': amount_today,
                'this_month': amount_this_month
            },
            'payments': {
                'pending': pending_payments,
                'pending_amount': pending_amount
            },
            'clients': {
                'total': total_clients
            }
        })
