from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.urls import include, path

from mailforge import portal_views, webmail_views


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
    path("mail/", webmail_views.webmail_home, name="webmail-home"),
    path("mail/connect/", webmail_views.webmail_connect, name="webmail-connect"),
    path(
        "mail/oauth/callback/",
        webmail_views.webmail_oauth_callback,
        name="webmail-oauth-callback",
    ),
    path("mail/inbox/", webmail_views.webmail_inbox, name="webmail-inbox"),
    path("mail/compose/", webmail_views.webmail_compose, name="webmail-compose"),
    path(
        "mail/messages/<str:email_id>/",
        webmail_views.webmail_message,
        name="webmail-message",
    ),
    path(
        "mail/messages/<str:source_id>/reply/",
        webmail_views.webmail_compose,
        {"mode": "reply"},
        name="webmail-reply",
    ),
    path(
        "mail/messages/<str:source_id>/reply-all/",
        webmail_views.webmail_compose,
        {"mode": "reply-all"},
        name="webmail-reply-all",
    ),
    path(
        "mail/messages/<str:source_id>/forward/",
        webmail_views.webmail_compose,
        {"mode": "forward"},
        name="webmail-forward",
    ),
    path(
        "mail/messages/<str:email_id>/attachments/<int:attachment_index>/",
        webmail_views.webmail_attachment,
        name="webmail-attachment",
    ),
    path(
        "mail/messages/<str:email_id>/unread/",
        webmail_views.webmail_mark_unread,
        name="webmail-mark-unread",
    ),
    path("mail/disconnect/", webmail_views.webmail_disconnect, name="webmail-disconnect"),
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
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/dns-check/",
        portal_views.domain_dns_check,
        name="portal-domain-dns-check",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/create/",
        portal_views.mailbox_create,
        name="portal-mailbox-create",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/<int:mailbox_pk>/suspend/",
        portal_views.mailbox_suspend,
        name="portal-mailbox-suspend",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/<int:mailbox_pk>/reactivate/",
        portal_views.mailbox_reactivate,
        name="portal-mailbox-reactivate",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/<int:mailbox_pk>/password-reset/",
        portal_views.mailbox_password_reset,
        name="portal-mailbox-password-reset",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/mailboxes/<int:mailbox_pk>/delete/",
        portal_views.mailbox_delete,
        name="portal-mailbox-delete",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/create/",
        portal_views.forwarder_create,
        name="portal-forwarder-create",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/<int:forwarder_pk>/update/",
        portal_views.forwarder_update,
        name="portal-forwarder-update",
    ),
    path(
        "portal/tenants/<slug:tenant_slug>/domains/<int:domain_pk>/forwarders/<int:forwarder_pk>/delete/",
        portal_views.forwarder_delete,
        name="portal-forwarder-delete",
    ),
    path("admin/", admin.site.urls),
    path("api/v1/", include("mailforge.api_urls")),
    path("health/", health),
]
