from django import forms

from .models import Category, Service, ServiceFormat


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Введите название.")
        exists = Category.objects.filter(
            name__iexact=name
        ).exclude(pk=self.instance.pk).exists()
        if exists:
            raise forms.ValidationError(
                "Категория с таким названием уже существует."
            )
        return name


class ServiceFormatForm(forms.ModelForm):
    class Meta:
        model = ServiceFormat
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Введите название.")
        exists = ServiceFormat.objects.filter(
            name__iexact=name
        ).exclude(pk=self.instance.pk).exists()
        if exists:
            raise forms.ValidationError(
                "Формат с таким названием уже существует."
            )
        return name


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            "category",
            "service_format",
            "name",
            "description",
            "price",
            "estimated_days",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "price": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
            "estimated_days": forms.NumberInput(
                attrs={"min": "0"}
            ),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Введите название.")
        return name

    def clean_price(self):
        value = self.cleaned_data["price"]
        if value < 0:
            raise forms.ValidationError(
                "Цена не может быть отрицательной."
            )
        return value

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        category = cleaned.get("category")
        if name and category:
            exists = Service.objects.filter(
                category=category,
                name__iexact=name,
            ).exclude(pk=self.instance.pk).exists()
            if exists:
                self.add_error(
                    "name",
                    "В этой категории уже есть услуга с таким названием.",
                )
        return cleaned
