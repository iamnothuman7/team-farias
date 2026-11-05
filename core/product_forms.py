import io
import re
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.core.files.base import ContentFile

from .models import Product


def style_fields(form):
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "checkbox" if isinstance(field.widget, forms.CheckboxInput) else "select" if isinstance(field.widget, forms.Select) else "input")


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "description", "image", "price", "sizes", "colors", "customize_name", "customize_number", "order_enabled", "is_active", "position"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}), "price": forms.NumberInput(attrs={"min": "0", "step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
        self.fields["image"].help_text = "JPG, PNG ou WebP de até 8 MB e 16 megapixels. A foto é otimizada e seus metadados são removidos."

    def clean_image(self):
        upload = self.cleaned_data.get("image")
        if not upload or not hasattr(upload, "content_type"):
            return upload
        if upload.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Envie uma foto de até 8 MB.")
        try:
            upload.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(upload) as original:
                    if original.format not in ("JPEG", "PNG", "WEBP") or original.width * original.height > 16_000_000:
                        raise ValueError
                    original.load()
                    img = ImageOps.exif_transpose(original).convert("RGBA" if "A" in original.getbands() else "RGB")
                    img.thumbnail((1600, 1600))
                    output = io.BytesIO()
                    img.save(output, format="WEBP", quality=88, exif=b"", icc_profile=b"")
            return ContentFile(output.getvalue(), name=f"{uuid.uuid4().hex}.webp")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError("Use uma imagem JPG, PNG ou WebP válida, de até 16 megapixels.")

    def clean_price(self):
        value = self.cleaned_data.get("price")
        if value is not None and value < 0:
            raise forms.ValidationError("O valor não pode ser negativo.")
        return value

    def _options(self, name, length):
        raw = self.cleaned_data[name]
        options = list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
        if len(options) > 15 or any(len(item) > length or any(ord(c) < 32 for c in item) for item in options):
            raise forms.ValidationError(f"Use até 15 opções, com até {length} caracteres cada.")
        return ", ".join(options)

    def clean_sizes(self):
        return self._options("sizes", 15)

    def clean_colors(self):
        return self._options("colors", 25)

    def clean(self):
        data = super().clean()
        if data.get("is_active") and not data.get("image"):
            self.add_error("image", "Adicione uma foto antes de publicar o produto.")
        return data


class ProductOrderForm(forms.Form):
    customer_name = forms.CharField(label="Seu nome", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    size = forms.ChoiceField(label="Tamanho")
    color = forms.ChoiceField(label="Cor")
    print_name = forms.CharField(label="Nome na camisa", max_length=24, help_text="Escreva exatamente como quer na estampa.")
    print_number = forms.RegexField(label="Número na camisa", regex=r"^[0-9]{1,2}$", max_length=2, widget=forms.TextInput(attrs={"inputmode": "numeric", "pattern": "[0-9]{1,2}"}), error_messages={"invalid": "Use um número de 0 a 99."})
    quantity = forms.IntegerField(label="Quantidade", min_value=1, max_value=50, initial=1, help_text="Peças com a mesma personalização. Para outras versões, prepare outro pedido.")
    notes = forms.CharField(label="Observações (opcional)", max_length=400, required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Algum detalhe para combinar com a equipe?"}))

    def __init__(self, *args, product, **kwargs):
        self.product = product
        super().__init__(*args, **kwargs)
        for field, options in (("size", product.size_options), ("color", product.color_options)):
            if options:
                self.fields[field].choices = [("", "Selecione")] + [(x, x) for x in options]
            else:
                del self.fields[field]
        if not product.customize_name:
            del self.fields["print_name"]
        if not product.customize_number:
            del self.fields["print_number"]
        style_fields(self)

    def clean(self):
        data = super().clean()
        for name in ("customer_name", "print_name"):
            if name in data:
                data[name] = re.sub(r"\s+", " ", data[name]).strip()
                if not data[name]:
                    self.add_error(name, "Preencha este campo.")
        return data

    def message(self):
        data = self.cleaned_data
        lines = ["Olá, Team Farias! Quero consultar este pedido:", "", f"Produto: {self.product.name} (#{self.product.pk})", f"Cliente: {data['customer_name']}"]
        for key, label in (("size", "Tamanho"), ("color", "Cor"), ("print_name", "Nome na estampa"), ("print_number", "Número na estampa")):
            if key in self.fields:
                lines.append(f"{label}: {data[key]}")
        lines.append(f"Quantidade: {data['quantity']}")
        if self.product.price is not None:
            lines.append(f"Valor de referência por unidade: R$ {self.product.price:.2f}".replace(".", ","))
        if data.get("notes"):
            lines.append(f"Observações: {data['notes']}")
        lines.extend(["", "Podem confirmar disponibilidade, valor final e prazo?"])
        return "\n".join(lines)
