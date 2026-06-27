# apps/ventes_clients/models.py
from django.db import models
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import qrcode
from io import BytesIO
from django.core.files import File

from users.models import CustomUser
from produits_stocks.models import Product, Lot, Warehouse


# ==================== CLIENT ====================
class Client(models.Model):
    """
    Client / Prospect
    """
    TYPE_CHOICES = (
        ('particulier', 'Particulier'),
        ('entreprise', 'Entreprise'),
        ('revendeur', 'Revendeur'),
        ('grossiste', 'Grossiste'),
    )
    
    STATUT_CHOICES = (
        ('actif', 'Actif'),
        ('inactif', 'Inactif'),
        ('bloque', 'Bloqué'),
    )
    
    # Identifiants
    code = models.CharField(max_length=50, unique=True, verbose_name="Code client")
    name = models.CharField(max_length=200, verbose_name="Nom / Raison sociale")
    commercial_name = models.CharField(max_length=200, blank=True, verbose_name="Nom commercial")
    
    # Type
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='particulier', verbose_name="Type")
    
    # Contacts
    contact_person = models.CharField(max_length=100, blank=True, verbose_name="Personne de contact")
    phone = models.CharField(max_length=20, verbose_name="Téléphone")
    mobile = models.CharField(max_length=20, blank=True, verbose_name="Mobile")
    email = models.EmailField(verbose_name="Email")
    website = models.URLField(blank=True, verbose_name="Site web")
    
    # Adresse
    address = models.TextField(verbose_name="Adresse")
    city = models.CharField(max_length=100, verbose_name="Ville")
    country = models.CharField(max_length=100, default='Sénégal', verbose_name="Pays")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Code postal")
    
    # Informations fiscales
    tax_id = models.CharField(max_length=50, blank=True, verbose_name="N° Identification fiscale")
    registration_number = models.CharField(max_length=50, blank=True, verbose_name="N° Registre de commerce")
    
    # Conditions commerciales
    payment_terms = models.CharField(max_length=20, choices=[
        ('cash', 'Comptant'),
        ('15', '15 jours'),
        ('30', '30 jours'),
        ('45', '45 jours'),
        ('60', '60 jours'),
    ], default='cash', verbose_name="Délai de paiement")
    
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Limite de crédit")
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Solde actuel")
    
    # Évaluation
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, verbose_name="Note (0-5)")
    total_purchases = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total achats")
    total_orders = models.IntegerField(default=0, verbose_name="Nombre de commandes")
    
    # Statut
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif', verbose_name="Statut")
    is_favorite = models.BooleanField(default=False, verbose_name="Client favori")
    notes = models.TextField(blank=True, verbose_name="Notes")
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date modification")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def full_address(self):
        parts = [self.address, self.city, self.country]
        return ", ".join([p for p in parts if p])


# ==================== VENTE ====================
class Vente(models.Model):
    """
    Vente / Bon de commande client
    """
    STATUS_CHOICES = (
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmée'),
        ('paid', 'Payée'),
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
        ('returned', 'Retournée'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'En attente'),
        ('partial', 'Paiement partiel'),
        ('paid', 'Payé'),
    )
    
    # Identifiants
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="N° Facture")
    order_number = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="N° Commande")
    
    # Client
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, related_name='sales')
    client_name = models.CharField(max_length=200, verbose_name="Nom client")
    client_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone client")
    client_email = models.EmailField(blank=True, verbose_name="Email client")
    client_address = models.TextField(blank=True, verbose_name="Adresse client")
    
    # Dates
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="Date vente")
    delivery_date = models.DateTimeField(null=True, blank=True, verbose_name="Date livraison")
    payment_due_date = models.DateField(verbose_name="Date échéance paiement")
    
    # Montants
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Sous-total")
    discount_type = models.CharField(max_length=20, choices=[
        ('percentage', 'Pourcentage'),
        ('amount', 'Montant')
    ], default='percentage', verbose_name="Type remise")
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valeur remise")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Montant remise")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Taux TVA (%)")
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Montant TVA")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Frais de livraison")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total TTC")
    
    # Paiement
    payment_method = models.CharField(max_length=50, blank=True, verbose_name="Méthode de paiement")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending', verbose_name="Statut paiement")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Montant payé")
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Montant dû")
    
    # Livraison
    delivery_method = models.CharField(max_length=50, blank=True, verbose_name="Méthode de livraison")
    delivery_address = models.TextField(verbose_name="Adresse de livraison")
    delivery_status = models.CharField(max_length=50, default='pending', verbose_name="Statut livraison")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="N° de suivi")
    
    # Statut
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Statut")
    notes = models.TextField(blank=True, verbose_name="Notes")
    internal_notes = models.TextField(blank=True, verbose_name="Notes internes")
    
    # QR Code
    qr_code = models.ImageField(upload_to='qrcodes/sales/', null=True, blank=True, verbose_name="QR Code")
    qr_code_data = models.TextField(blank=True, verbose_name="Données QR Code")
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date modification")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales',
        verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        ordering = ['-sale_date']

    def __str__(self):
        return f"{self.invoice_number} - {self.client_name}"

    def calculate_totals(self):
        """Calcule les totaux de la vente"""
        self.subtotal = sum(line.total for line in self.lines.all())
        
        if self.discount_type == 'percentage':
            self.discount_amount = self.subtotal * (self.discount_value / 100)
        else:
            self.discount_amount = self.discount_value
        
        after_discount = self.subtotal - self.discount_amount
        self.tax_amount = after_discount * (self.tax_rate / 100)
        self.total = after_discount + self.tax_amount + self.shipping_fee
        self.amount_due = self.total - self.amount_paid
        
        if self.amount_due <= 0:
            self.payment_status = 'paid'
        elif self.amount_paid > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'pending'
        
        self.save()

    def generate_qr_code(self):
        """Génère un QR Code pour la vente"""
        if not self.invoice_number:
            return
            
        import json
        qr_data = {
            'type': 'sale',
            'id': self.id,
            'number': self.invoice_number,
            'client': self.client_name,
            'total': str(self.total),
            'date': self.sale_date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': self.status,
            'url': f'/ventes/{self.id}/'
        }
        
        qr_data_str = json.dumps(qr_data, ensure_ascii=False)
        self.qr_code_data = qr_data_str
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data_str)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        
        filename = f"qr_sale_{self.invoice_number}.png"
        self.qr_code.save(filename, File(buffer), save=False)
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.qr_code or not self.qr_code_data:
            self.generate_qr_code()
            super().save(update_fields=['qr_code', 'qr_code_data'])


# ==================== LIGNE VENTE ====================
class LigneVente(models.Model):
    """
    Ligne de vente
    """
    sale = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True)
    
    quantity = models.IntegerField(verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix unitaire")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Remise")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="TVA (%)")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total ligne")
    
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

    def __str__(self):
        return f"{self.sale.invoice_number} - {self.product.name}"

    def save(self, *args, **kwargs):
        self.total = (self.quantity * self.unit_price) - self.discount
        super().save(*args, **kwargs)
        self.sale.calculate_totals()


# ==================== PAIEMENT ====================
class Paiement(models.Model):
    """
    Paiement client
    """
    METHOD_CHOICES = (
        ('cash', 'Espèces'),
        ('card', 'Carte bancaire'),
        ('check', 'Chèque'),
        ('transfer', 'Virement'),
        ('mobile_money', 'Mobile Money'),
        ('credit', 'Crédit'),
    )
    
    sale = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, verbose_name="Méthode")
    reference = models.CharField(max_length=100, blank=True, verbose_name="Référence")
    payment_date = models.DateTimeField(auto_now_add=True, verbose_name="Date paiement")
    received_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="Reçu par")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.sale.invoice_number} - {self.amount} FCFA"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sale.amount_paid = self.sale.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        self.sale.amount_due = self.sale.total - self.sale.amount_paid
        
        if self.sale.amount_due <= 0:
            self.sale.payment_status = 'paid'
        elif self.sale.amount_paid > 0:
            self.sale.payment_status = 'partial'
        else:
            self.sale.payment_status = 'pending'
        self.sale.save()


# ==================== FACTURE ====================
class Facture(models.Model):
    """
    Facture client
    """
    STATUS_CHOICES = (
        ('draft', 'Brouillon'),
        ('sent', 'Envoyée'),
        ('paid', 'Payée'),
        ('overdue', 'En retard'),
        ('cancelled', 'Annulée'),
    )
    
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="N° Facture")
    sale = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='invoices')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    
    invoice_date = models.DateField(auto_now_add=True, verbose_name="Date facture")
    due_date = models.DateField(verbose_name="Date échéance")
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Sous-total")
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="TVA")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total")
    
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Montant payé")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Statut")
    
    pdf_file = models.FileField(upload_to='invoices/', null=True, blank=True, verbose_name="PDF facture")
    notes = models.TextField(blank=True, verbose_name="Notes")
    
    # QR Code
    qr_code = models.ImageField(upload_to='qrcodes/invoices/', null=True, blank=True, verbose_name="QR Code")
    qr_code_data = models.TextField(blank=True, verbose_name="Données QR Code")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        ordering = ['-invoice_date']

    def __str__(self):
        return f"{self.invoice_number} - {self.client.name}"

    @property
    def remaining_amount(self):
        return self.total - self.amount_paid

    def generate_qr_code(self):
        """Génère un QR Code pour la facture"""
        if not self.invoice_number:
            return
            
        import json
        qr_data = {
            'type': 'invoice',
            'id': self.id,
            'number': self.invoice_number,
            'client': self.client.name,
            'total': str(self.total),
            'date': self.invoice_date.strftime('%Y-%m-%d'),
            'due_date': self.due_date.strftime('%Y-%m-%d'),
            'status': self.status,
            'url': f'/factures/{self.id}/'
        }
        
        qr_data_str = json.dumps(qr_data, ensure_ascii=False)
        self.qr_code_data = qr_data_str
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data_str)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        
        filename = f"qr_invoice_{self.invoice_number}.png"
        self.qr_code.save(filename, File(buffer), save=False)
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.qr_code or not self.qr_code_data:
            self.generate_qr_code()
            super().save(update_fields=['qr_code', 'qr_code_data'])


# ==================== AVOIR ====================
class Avoir(models.Model):
    """
    Avoir / Note de crédit
    """
    TYPE_CHOICES = (
        ('credit', 'Avoir'),
        ('debit', 'Note de débit'),
    )
    
    avoir_number = models.CharField(max_length=50, unique=True, verbose_name="N° Avoir")
    sale = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='credits')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='credits')
    
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='credit', verbose_name="Type")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant")
    reason = models.TextField(verbose_name="Raison")
    
    date = models.DateField(auto_now_add=True, verbose_name="Date")
    notes = models.TextField(blank=True, verbose_name="Notes")
    
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Avoir"
        verbose_name_plural = "Avoirs"
        ordering = ['-date']

    def __str__(self):
        return f"{self.avoir_number} - {self.client.name} - {self.amount} FCFA"


# ==================== TAXE ====================
class Taxe(models.Model):
    """
    Configuration des taxes
    """
    name = models.CharField(max_length=100, verbose_name="Nom")
    rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Taux (%)")
    is_default = models.BooleanField(default=False, verbose_name="Par défaut")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Taxe"
        verbose_name_plural = "Taxes"

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


# ==================== REMISE ====================
class Remise(models.Model):
    """
    Remise / Réduction
    """
    TYPE_CHOICES = (
        ('percentage', 'Pourcentage'),
        ('amount', 'Montant fixe'),
    )
    
    name = models.CharField(max_length=100, verbose_name="Nom")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type")
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valeur")
    
    min_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Achat minimum")
    start_date = models.DateField(null=True, blank=True, verbose_name="Date début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Date fin")
    
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    clients = models.ManyToManyField(Client, blank=True, verbose_name="Clients concernés")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Remise"
        verbose_name_plural = "Remises"

    def __str__(self):
        return f"{self.name} - {self.value}{'%' if self.type == 'percentage' else ' FCFA'}"


# ==================== POINT DE VENTE ====================
class PointDeVente(models.Model):
    """
    Point de vente / Caisse
    """
    name = models.CharField(max_length=100, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, verbose_name="Entrepôt associé")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Point de vente"
        verbose_name_plural = "Points de vente"

    def __str__(self):
        return self.name


# ==================== SESSION CAISSE ====================
class SessionCaisse(models.Model):
    """
    Session de caisse
    """
    STATUS_CHOICES = (
        ('open', 'Ouverte'),
        ('closed', 'Fermée'),
        ('suspended', 'Suspendue'),
    )
    
    point_de_vente = models.ForeignKey(PointDeVente, on_delete=models.CASCADE, related_name='sessions')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='cash_sessions')
    
    opening_date = models.DateTimeField(auto_now_add=True, verbose_name="Date ouverture")
    closing_date = models.DateTimeField(null=True, blank=True, verbose_name="Date fermeture")
    
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Solde d'ouverture")
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Solde de fermeture")
    expected_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Solde attendu")
    difference = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Différence")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name="Statut")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Session de caisse"
        verbose_name_plural = "Sessions de caisse"

    def __str__(self):
        return f"{self.point_de_vente.name} - {self.user.email} - {self.opening_date}"


# ==================== MOUVEMENT CAISSE ====================
class MouvementCaisse(models.Model):
    """
    Mouvement de caisse
    """
    TYPE_CHOICES = (
        ('sale', 'Vente'),
        ('payment', 'Paiement'),
        ('deposit', 'Dépôt'),
        ('withdrawal', 'Retrait'),
        ('expense', 'Dépense'),
    )
    
    session = models.ForeignKey(SessionCaisse, on_delete=models.CASCADE, related_name='movements')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant")
    description = models.CharField(max_length=200, verbose_name="Description")
    reference = models.CharField(max_length=100, blank=True, verbose_name="Référence")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Mouvement de caisse"
        verbose_name_plural = "Mouvements de caisse"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.type} - {self.amount} FCFA"