from django.contrib import admin
from django.urls import include, path

from studio import api, client_orders, views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("reports/", views.report),
    path("api/register/", api.register),
    path("api/login/", api.login),
    path("api/services/", api.services),
    path("api/orders/", client_orders.order_list),
    path("api/orders/create/", api.create_order),
    path("api/notifications/", api.notifications),
    path(
        "api/orders/<int:pk>/",
        client_orders.order_detail,
    ),
    path(
        "api/orders/<int:pk>/update/",
        client_orders.order_update,
    ),
    path(
        "api/orders/<int:pk>/delete/",
        client_orders.order_delete,
    ),
    path("catalog/", include("studio.catalog_urls")),
    path("", include("studio.web_urls")),

]