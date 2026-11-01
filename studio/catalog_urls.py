from django.urls import path

from . import catalog_views

app_name = "studio_catalog"

urlpatterns = [
    path("clients/", catalog_views.client_list, name="clients"),
    path(
        "clients/<int:pk>/",
        catalog_views.client_detail,
        name="client_detail",
    ),
    path("<str:kind>/", catalog_views.catalog_list, name="list"),
    path("<str:kind>/new/", catalog_views.catalog_edit, name="create"),
    path(
        "<str:kind>/<int:pk>/",
        catalog_views.catalog_detail,
        name="detail",
    ),
    path(
        "<str:kind>/<int:pk>/edit/",
        catalog_views.catalog_edit,
        name="edit",
    ),
    path(
        "<str:kind>/<int:pk>/delete/",
        catalog_views.catalog_delete,
        name="delete",
    ),
]
