from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.urls import include, path

from mailforge import portal_views


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", portal_views.dashboard, name="dashboard"),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("portal/tenants/create/", portal_views.tenant_create, name="portal-tenant-create"),
    path(
        "portal/tenants/<slug:tenant_slug>/",
        portal_views.tenant_detail,
        name="portal-tenant",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/create/",
        portal_views.domain_create,
        name="portal-domain-create",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/",
        portal_views.domain_detail,
        name="portal-domain",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/verify/",
        portal_views.domain_verify,
        name="portal-domain-verify",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/provision/",
        portal_views.domain_provision,
        name="portal-domain-provision",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/create/",
        portal_views.forwarder_create,
        name="portal-forwarder-create",
    ),
    path("admin/", admin.site.urls),
    path("api/v1/", include("mailforge.api_urls")),
    path("health/", health),
]
