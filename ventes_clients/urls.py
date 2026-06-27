# apps/ventes_clients/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet, VenteViewSet, PaiementViewSet,
    FactureViewSet, AvoirViewSet, TaxeViewSet,
    RemiseViewSet, PointDeVenteViewSet, SessionCaisseViewSet,
    SalesDashboardStatsViewSet
)

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='clients')
router.register('sales', VenteViewSet, basename='sales')
router.register('payments', PaiementViewSet, basename='payments')
router.register('factures', FactureViewSet, basename='factures')
router.register('avoirs', AvoirViewSet, basename='avoirs')
router.register('taxes', TaxeViewSet, basename='taxes')
router.register('remises', RemiseViewSet, basename='remises')
router.register('points-de-vente', PointDeVenteViewSet, basename='points-de-vente')
router.register('sessions-caisse', SessionCaisseViewSet, basename='sessions-caisse')
router.register('dashboard-sales-stats', SalesDashboardStatsViewSet, basename='dashboard-sales-stats')

urlpatterns = [
    path('', include(router.urls)),
]