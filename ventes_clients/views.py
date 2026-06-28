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
    """
    ViewSet pour la gestion des clients
    """
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
    """
    ViewSet pour la gestion des ventes
    """
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

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a237e'),
            alignment=TA_CENTER,
            spaceAfter=30
        )
        elements.append(Paragraph("FACTURE", title_style))

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

        if vente.notes:
            elements.append(Paragraph("<b>Notes:</b>", info_style))
            elements.append(Paragraph(vente.notes, info_style))

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


# ==================== FACTURE VIEWSET ====================
# apps/ventes_clients/views.py - FactureViewSet

# apps/ventes_clients/views.py - FactureViewSet complet

# ==================== FACTURE VIEWSET ====================
class FactureViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des factures clients
    """
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

        # Filtrer par client
        client = self.request.query_params.get('client')
        if client:
            queryset = queryset.filter(client_id=client)

        # Filtrer par statut (supporte plusieurs statuts séparés par des virgules)
        status = self.request.query_params.get('status')
        if status:
            status_list = status.split(',')
            queryset = queryset.filter(status__in=status_list)

        # Filtrer par date
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(invoice_date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(invoice_date__lte=date_to)

        # Filtrer par recherche
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search) |
                Q(client__name__icontains=search) |
                Q(client__code__icontains=search)
            )

        return queryset

    @action(detail=True, methods=['post'])
    def register_payment(self, request, pk=None):
        """
        Enregistre un paiement sur une facture
        """
        from decimal import Decimal
        from django.db import transaction
        from django.db.models import Sum

        facture = self.get_object()

        amount = request.data.get('amount')
        method = request.data.get('method', 'cash')
        reference = request.data.get('reference', '')
        notes = request.data.get('notes', '')

        # Valider et convertir le montant
        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return Response(
                {"error": "Le montant doit être un nombre valide"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount <= 0:
            return Response(
                {"error": "Le montant doit être supérieur à 0"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount > facture.remaining_amount:
            return Response(
                {"error": f"Le montant dépasse le solde restant ({facture.remaining_amount})"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # 1. Créer le paiement
            paiement = Paiement.objects.create(
                facture=facture,
                amount=amount,
                method=method,
                reference=reference,
                notes=notes or f"Paiement sur la facture {facture.invoice_number}",
                received_by=request.user
            )

            # 2. Mettre à jour la facture
            total_paid = facture.paiements.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            facture.amount_paid = total_paid
            if facture.amount_paid >= facture.total:
                facture.status = 'paid'
            elif facture.amount_paid > 0:
                facture.status = 'partial'
            facture.save()

            # 3. Mettre à jour la vente associée
            sale = facture.sale
            if sale:
                # Calculer le total payé sur toutes les factures de cette vente
                total_paid_sale = Decimal('0')
                for inv in sale.invoices.all():
                    total_paid_sale += inv.amount_paid

                sale.amount_paid = total_paid_sale
                sale.amount_due = sale.total - sale.amount_paid

                if sale.amount_due <= 0:
                    sale.payment_status = 'paid'
                elif sale.amount_paid > 0:
                    sale.payment_status = 'partial'
                else:
                    sale.payment_status = 'pending'
                sale.save()

        from .serializers import PaiementSerializer
        serializer = PaiementSerializer(paiement)

        return Response({
            'paiement': serializer.data,
            'facture': FactureSerializer(facture, context={'request': request}).data,
            'remaining_amount': facture.remaining_amount
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """
        Marque une facture comme payée (méthode alternative)
        """
        from decimal import Decimal
        from django.db import transaction
        from django.db.models import Sum

        facture = self.get_object()

        amount = request.data.get('amount', 0)
        method = request.data.get('method', 'cash')
        reference = request.data.get('reference', '')
        notes = request.data.get('notes', '')

        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return Response(
                {"error": "Le montant doit être un nombre valide"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount <= 0:
            return Response(
                {"error": "Le montant doit être supérieur à 0"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if amount > facture.remaining_amount:
            return Response(
                {"error": f"Le montant dépasse le solde restant ({facture.remaining_amount})"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # 1. Créer le paiement
            paiement = Paiement.objects.create(
                facture=facture,
                amount=amount,
                method=method,
                reference=reference,
                notes=notes or f"Paiement sur la facture {facture.invoice_number}",
                received_by=request.user
            )

            # 2. Mettre à jour la facture
            total_paid = facture.paiements.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            facture.amount_paid = total_paid
            if facture.amount_paid >= facture.total:
                facture.status = 'paid'
            elif facture.amount_paid > 0:
                facture.status = 'partial'
            facture.save()

            # 3. Mettre à jour la vente associée
            sale = facture.sale
            if sale:
                total_paid_sale = Decimal('0')
                for inv in sale.invoices.all():
                    total_paid_sale += inv.amount_paid

                sale.amount_paid = total_paid_sale
                sale.amount_due = sale.total - sale.amount_paid

                if sale.amount_due <= 0:
                    sale.payment_status = 'paid'
                elif sale.amount_paid > 0:
                    sale.payment_status = 'partial'
                else:
                    sale.payment_status = 'pending'
                sale.save()

        from .serializers import PaiementSerializer
        serializer = PaiementSerializer(paiement)

        return Response({
            'paiement': serializer.data,
            'facture_status': facture.status,
            'remaining_amount': facture.remaining_amount
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """
        Marque la facture comme envoyée
        """
        facture = self.get_object()

        if facture.status != 'draft':
            return Response(
                {"error": "Seules les factures en brouillon peuvent être envoyées"},
                status=status.HTTP_400_BAD_REQUEST
            )

        facture.status = 'sent'
        facture.save()

        # Générer le QR Code
        facture.generate_qr_code()
        facture.save()

        return Response({
            'status': facture.status,
            'message': 'Facture envoyée avec succès'
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annule une facture
        """
        facture = self.get_object()

        if facture.status in ['paid']:
            return Response(
                {"error": "Les factures payées ne peuvent pas être annulées"},
                status=status.HTTP_400_BAD_REQUEST
            )

        facture.status = 'cancelled'
        facture.save()

        return Response({
            'status': facture.status,
            'message': 'Facture annulée avec succès'
        })

    @action(detail=True, methods=['post'])
    def generate_invoice(self, request, pk=None):
        """
        Génère une facture à partir d'une vente (méthode alternative)
        """
        from django.db import transaction
        from datetime import date

        sale_id = request.data.get('sale_id')
        due_date = request.data.get('due_date')

        if not sale_id:
            return Response(
                {"error": "L'ID de la vente est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sale = Vente.objects.get(id=sale_id)
        except Vente.DoesNotExist:
            return Response(
                {"error": "Vente non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )

        if Facture.objects.filter(sale=sale).exists():
            return Response(
                {"error": "Une facture existe déjà pour cette vente"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if due_date:
            try:
                due_date = date.fromisoformat(due_date)
            except ValueError:
                return Response(
                    {"error": "Format de date invalide. Utilisez YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            due_date = date.today() + timedelta(days=30)

        with transaction.atomic():
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
                sale=sale,
                client=sale.client,
                due_date=due_date,
                subtotal=sale.subtotal,
                tax_amount=sale.tax_amount,
                total=sale.total,
                status='draft'
            )

            facture.generate_qr_code()
            facture.save()

        return Response({
            'facture': FactureSerializer(facture, context={'request': request}).data,
            'message': 'Facture générée avec succès'
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def generate_qr(self, request, pk=None):
        """
        Génère et retourne le QR Code de la facture
        """
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

    @action(detail=True, methods=['get'])
    def paiements(self, request, pk=None):
        """
        Récupère tous les paiements d'une facture
        """
        facture = self.get_object()
        paiements = facture.paiements.all()

        from .serializers import PaiementSerializer
        serializer = PaiementSerializer(paiements, many=True)

        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """
        Génère un PDF de la facture avec QR Code
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER
        from io import BytesIO
        from PIL import Image as PILImage

        facture = self.get_object()

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
            Paragraph(f"<b>N° Facture:</b> {facture.invoice_number}", info_style))
        elements.append(Paragraph(
            f"<b>Date:</b> {facture.invoice_date.strftime('%d/%m/%Y')}", info_style))
        elements.append(
            Paragraph(f"<b>Client:</b> {facture.client.name}", info_style))
        elements.append(Paragraph(
            f"<b>Échéance:</b> {facture.due_date.strftime('%d/%m/%Y')}", info_style))
        elements.append(
            Paragraph(f"<b>Statut:</b> {facture.get_status_display()}", info_style))
        elements.append(Spacer(1, 12))

        # QR Code
        if facture.qr_code:
            try:
                qr_path = facture.qr_code.path
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

        # Tableau des montants
        data = [
            ['Sous-total', f"{facture.subtotal:,.0f} FCFA"],
            ['TVA', f"{facture.tax_amount:,.0f} FCFA"],
            ['Total', f"{facture.total:,.0f} FCFA"],
            ['Montant payé', f"{facture.amount_paid:,.0f} FCFA"],
            ['Reste à payer', f"{facture.remaining_amount:,.0f} FCFA"]
        ]

        table = Table(data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -2), 1, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 20))

        # Notes
        if facture.notes:
            elements.append(Paragraph("<b>Notes:</b>", info_style))
            elements.append(Paragraph(facture.notes, info_style))

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
        response['Content-Disposition'] = f'attachment; filename="facture_{facture.invoice_number}.pdf"'
        return response
# ==================== PAIEMENT VIEWSET ====================

# apps/ventes_clients/views.py


class PaiementViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des paiements
    """
    queryset = Paiement.objects.all()
    serializer_class = PaiementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        queryset = super().get_queryset()

        facture_id = self.request.query_params.get('facture')
        if facture_id:
            queryset = queryset.filter(facture_id=facture_id)

        return queryset

    def perform_create(self, serializer):
        paiement = serializer.save(received_by=self.request.user)
        # ✅ Générer le QR Code après création
        paiement.generate_qr_code()
        paiement.save()

    @action(detail=True, methods=['get'])
    def generate_qr(self, request, pk=None):
        """
        Génère et retourne le QR Code du paiement
        """
        paiement = self.get_object()

        if not paiement.qr_code:
            paiement.generate_qr_code()
            paiement.save()

        if paiement.qr_code:
            return Response({
                'qr_code_url': request.build_absolute_uri(paiement.qr_code.url),
                'qr_code_data': paiement.qr_code_data
            })

        return Response(
            {"error": "Impossible de générer le QR Code"},
            status=500
        )

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """
        Génère un PDF du reçu de paiement avec QR Code
        """
        paiement = self.get_object()

        # ✅ Générer le QR Code si nécessaire
        if not paiement.qr_code:
            paiement.generate_qr_code()
            paiement.save()

        # Utiliser la fonction existante du frontend ou générer le PDF ici
        # Si vous voulez générer le PDF côté backend, vous pouvez l'ajouter ici
        from django.http import HttpResponse
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, mm
        from reportlab.lib.enums import TA_CENTER
        from io import BytesIO
        from PIL import Image as PILImage

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # ... Génération du PDF avec QR Code ...
        # Vous pouvez utiliser le QR Code stocké dans paiement.qr_code

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="recu_paiement_{paiement.id}.pdf"'
        return response


# ==================== AVOIR VIEWSET ====================
class AvoirViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des avoirs
    """
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
    """
    ViewSet pour la gestion des taxes
    """
    queryset = Taxe.objects.all()
    serializer_class = TaxeSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


# ==================== REMISE VIEWSET ====================
class RemiseViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des remises
    """
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
    """
    ViewSet pour la gestion des points de vente
    """
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
    """
    ViewSet pour la gestion des sessions de caisse
    """
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
        """Ferme une session de caisse"""
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
        """Ajoute un mouvement à une session de caisse"""
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
    """
    ViewSet pour les statistiques du dashboard des ventes
    """
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
