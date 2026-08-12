from django.urls import path

from apps.domains.api import (
    TenantDomainDetailView,
    TenantDomainListCreateView,
    TenantDomainProvisionView,
    TenantDomainVerifyView,
)
from apps.tenants.api import TenantDetailView, TenantListCreateView


urlpatterns = [
    path("tenants/", TenantListCreateView.as_view(), name="tenant-list-create"),
    path("tenants/<slug:slug>/", TenantDetailView.as_view(), name="tenant-detail"),
    path(
        "tenants/<slug:tenant_slug>/domains/",
        TenantDomainListCreateView.as_view(),
        name="tenant-domain-list-create",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:pk>/",
        TenantDomainDetailView.as_view(),
        name="tenant-domain-detail",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:pk>/verify/",
        TenantDomainVerifyView.as_view(),
        name="tenant-domain-verify",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:pk>/provision/",
        TenantDomainProvisionView.as_view(),
        name="tenant-domain-provision",
    ),
]
