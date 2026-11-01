from django.urls import path

from . import web_views

app_name = "studio_web"

urlpatterns = [
    path("", web_views.order_list, name="order_list"),
    path("login/", web_views.StaffLoginView.as_view(), name="login"),
    path("logout/", web_views.staff_logout, name="logout"),
    path("orders/new/", web_views.order_edit, name="order_create"),
    path("orders/<int:pk>/", web_views.order_detail, name="order_detail"),
    path("orders/<int:pk>/edit/", web_views.order_edit, name="order_edit"),
    path(
        "orders/<int:pk>/delete/",
        web_views.order_delete,
        name="order_delete",
    ),
]
