from django.contrib import messages
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .catalog_forms import CategoryForm, ServiceForm, ServiceFormatForm
from .models import Category, Client, Service, ServiceFormat
from .roles import staff_only


CATALOGS = {
    "services": {
        "model": Service,
        "form": ServiceForm,
        "title": "Услуги",
        "singular": "Услуга",
        "fields": [
            ("name", "Название"),
            ("category", "Категория"),
            ("service_format", "Формат"),
            ("price", "Цена, ₽"),
            ("estimated_days", "Срок, дней"),
            ("is_active", "Доступна"),
            ("description", "Описание"),
        ],
    },
    "categories": {
        "model": Category,
        "form": CategoryForm,
        "title": "Категории",
        "singular": "Категория",
        "fields": [
            ("name", "Название"),
            ("description", "Описание"),
        ],
    },
    "formats": {
        "model": ServiceFormat,
        "form": ServiceFormatForm,
        "title": "Форматы услуг",
        "singular": "Формат услуги",
        "fields": [
            ("name", "Название"),
            ("description", "Описание"),
        ],
    },
}


def get_catalog(kind):
    if kind not in CATALOGS:
        raise Http404("Раздел не найден.")
    return CATALOGS[kind]


@staff_only
@require_GET
def catalog_list(request, kind):
    spec = get_catalog(kind)
    items = spec["model"].objects.all()
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")

    allowed_sorts = {
        "name": "По названию: А–Я",
        "-name": "По названию: Я–А",
    }

    if kind == "services":
        items = items.select_related("category", "service_format")
        allowed_sorts.update({
            "price": "По цене: возрастание",
            "-price": "По цене: убывание",
        })

        active = request.GET.get("active", "")
        if active in ("yes", "no"):
            items = items.filter(is_active=active == "yes")
        else:
            active = ""
    else:
        active = ""

    if query:
        items = items.filter(name__icontains=query)

    if sort not in allowed_sorts:
        sort = "name"

    return render(
        request,
        "studio/web/catalog_list.html",
        {
            "kind": kind,
            "spec": spec,
            "items": items.order_by(sort, "pk"),
            "query": query,
            "selected_sort": sort,
            "sort_options": allowed_sorts.items(),
            "active": active,
        },
    )


@staff_only
@require_GET
def catalog_detail(request, kind, pk):
    spec = get_catalog(kind)
    obj = get_object_or_404(spec["model"], pk=pk)

    details = []
    for field, label in spec["fields"]:
        value = getattr(obj, field)
        if isinstance(value, bool):
            value = "Да" if value else "Нет"
        elif value is None or value == "":
            value = "—"
        details.append((label, value))

    return render(
        request,
        "studio/web/catalog_detail.html",
        {
            "kind": kind,
            "spec": spec,
            "obj": obj,
            "details": details,
        },
    )


@staff_only
@require_http_methods(["GET", "POST"])
def catalog_edit(request, kind, pk=None):
    spec = get_catalog(kind)
    obj = get_object_or_404(spec["model"], pk=pk) if pk else None

    form = spec["form"](
        request.POST if request.method == "POST" else None,
        instance=obj,
    )

    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, "Запись сохранена.")
        return redirect(
            "studio_catalog:detail",
            kind=kind,
            pk=saved.pk,
        )

    return render(
        request,
        "studio/web/catalog_form.html",
        {
            "kind": kind,
            "spec": spec,
            "form": form,
            "obj": obj,
        },
    )


@staff_only
@require_http_methods(["GET", "POST"])
def catalog_delete(request, kind, pk):
    spec = get_catalog(kind)
    obj = get_object_or_404(spec["model"], pk=pk)

    if request.method == "POST":
        try:
            obj.delete()
        except ProtectedError:
            messages.error(
                request,
                "Запись используется в других данных и не может быть "
                "удалена. Для услуги можно отключить доступность.",
            )
            return redirect(
                "studio_catalog:detail",
                kind=kind,
                pk=pk,
            )

        messages.success(request, "Запись удалена.")
        return redirect("studio_catalog:list", kind=kind)

    return render(
        request,
        "studio/web/catalog_delete.html",
        {"kind": kind, "spec": spec, "obj": obj},
    )


@staff_only
@require_GET
def client_list(request):
    query = request.GET.get("q", "").strip()
    items = Client.objects.all()

    if query:
        from django.db.models import Q
        items = items.filter(
            Q(full_name__icontains=query)
            | Q(phone__icontains=query)
        )

    return render(
        request,
        "studio/web/client_list.html",
        {
            "clients": items.order_by("full_name", "pk"),
            "query": query,
        },
    )


@staff_only
@require_GET
def client_detail(request, pk):
    obj = get_object_or_404(
        Client.objects.select_related("user"),
        pk=pk,
    )

    return render(
        request,
        "studio/web/client_detail.html",
        {
            "client_obj": obj,
            "orders": obj.orders.select_related(
                "service"
            ).order_by("-created_at"),
        },
    )
