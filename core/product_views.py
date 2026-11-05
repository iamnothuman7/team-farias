from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from dashboard.decorators import staff_required
from .models import Product, SiteConfiguration
from .product_forms import ProductForm, ProductOrderForm


def catalog(request, internal=False):
    return render(request, "products/catalog.html", {"products": Product.objects.filter(is_active=True), "base_template": "base_app.html" if internal else "base.html", "internal_catalog": internal})


@login_required
def app_catalog(request):
    return catalog(request, internal=True)


@require_http_methods(["GET", "POST"])
def product_detail(request, pk, internal=False):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    form = ProductOrderForm(request.POST or None, product=product)
    context = {"product": product, "form": form, "base_template": "base_app.html" if internal else "base.html", "internal_catalog": internal}
    if request.method == "POST":
        if not product.order_enabled:
            form.add_error(None, "Os pedidos deste produto estão pausados. Consulte outro item do catálogo.")
        elif form.is_valid() and request.POST.get("action") != "edit":
            context["order_message"] = form.message()
            context["whatsapp_url"] = "https://wa.me/" + SiteConfiguration.current().whatsapp + "?" + urlencode({"text": form.message()})
    return render(request, "products/detail.html", context)


@login_required
def app_product_detail(request, pk):
    return product_detail(request, pk, internal=True)


@staff_required
def manage_products(request):
    return render(request, "products/manage.html", {"products": Product.objects.all()})


@staff_required
@require_http_methods(["GET", "POST"])
def edit_product(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Produto salvo. Confira a publicação no catálogo.")
        return redirect("dashboard:products")
    return render(request, "products/edit.html", {"form": form, "product": product})
