from django.urls import path

from apps.domains.api import (
    TenantDomainDetailView,
    TenantDomainListCreateView,
    TenantDomainProvisionView,
    TenantDomainVerifyView,
)
from apps.mailboxes.api import (
    TenantForwarderDetailView,
    TenantForwarderListCreateView,
    TenantMailboxDetailView,
    TenantMailboxListCreateView,
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
    path(
        "tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/",
        TenantMailboxListCreateView.as_view(),
        name="tenant-mailbox-list-create",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/<int:pk>/",
        TenantMailboxDetailView.as_view(),
        name="tenant-mailbox-detail",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/",
        TenantForwarderListCreateView.as_view(),
        name="tenant-forwarder-list-create",
    ),
    path(
        "tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/<int:pk>/",
        TenantForwarderDetailView.as_view(),
        name="tenant-forwarder-detail",
    ),
]
