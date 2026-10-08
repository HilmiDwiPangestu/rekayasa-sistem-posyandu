"""Reusable form UX helpers for the Posyandu application.

This module keeps server-side validation authoritative while making the
messages shown to users consistent, Indonesian, and suitable for black-box
usability testing.
"""
from django import forms


class IndonesianValidationMixin:
    """Apply consistent Indonesian validation messages and helpful placeholders.

    The mixin intentionally does not change which fields are required. Business
    rules remain owned by each concrete form; this class only improves the UX
    for the rules that already exist.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            label = str(field.label or name.replace("_", " ").title()).strip()
            widget = field.widget

            is_choice = isinstance(
                field,
                (
                    forms.ChoiceField,
                    forms.MultipleChoiceField,
                    forms.ModelChoiceField,
                    forms.ModelMultipleChoiceField,
                ),
            )

            field.error_messages["required"] = (
                f"{label} wajib dipilih." if is_choice else f"{label} wajib diisi."
            )
            field.error_messages["invalid"] = f"Format {label} tidak valid."
            field.error_messages["invalid_choice"] = f"Pilihan {label} tidak valid."
            field.error_messages["invalid_list"] = f"Pilihan {label} tidak valid."
            if "max_length" in field.error_messages:
                field.error_messages["max_length"] = f"{label} terlalu panjang."
            if "min_length" in field.error_messages:
                field.error_messages["min_length"] = f"{label} terlalu pendek."
            if "max_value" in field.error_messages:
                field.error_messages["max_value"] = f"Nilai {label} melebihi batas maksimum."
            if "min_value" in field.error_messages:
                field.error_messages["min_value"] = f"Nilai {label} kurang dari batas minimum."

            if field.required:
                widget.attrs.setdefault("aria-required", "true")

            # Replace Django's generic dashed option with a useful prompt.
            if isinstance(field, forms.ModelChoiceField) and field.empty_label == "---------":
                field.empty_label = f"Pilih {label}"
            elif isinstance(field, forms.ChoiceField) and not isinstance(field, forms.ModelChoiceField):
                try:
                    choices = list(field.choices)
                    if choices and choices[0][0] in ("", None) and str(choices[0][1]).strip() in {"---------", ""}:
                        choices[0] = (choices[0][0], f"Pilih {label}")
                        field.choices = choices
                except (TypeError, AttributeError):
                    pass

            # Add a fallback placeholder only when the concrete form did not
            # already define a more specific one.
            if "placeholder" not in widget.attrs and isinstance(
                widget,
                (
                    forms.TextInput,
                    forms.EmailInput,
                    forms.URLInput,
                    forms.NumberInput,
                    forms.PasswordInput,
                    forms.Textarea,
                ),
            ):
                if isinstance(widget, forms.EmailInput):
                    placeholder = "contoh@email.com"
                elif isinstance(widget, forms.PasswordInput):
                    placeholder = f"Masukkan {label.lower()}"
                else:
                    placeholder = f"Masukkan {label.lower()}"
                widget.attrs["placeholder"] = placeholder
