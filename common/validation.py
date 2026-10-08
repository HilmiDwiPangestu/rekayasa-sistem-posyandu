"""Helpers for translating model/service validation into normal form errors."""
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError


def add_validation_error(form, error, *, fallback_field=None):
    """Attach a Django ValidationError to a bound form without raising a 500 page.

    Model ``save()`` methods in this project call ``full_clean()``. If a
    validation rule is evaluated only after relations/role values are assigned,
    the resulting ValidationError must be moved back to the form so the user can
    correct the input and the SweetAlert validation UI can present it.
    """
    if not isinstance(error, ValidationError):
        error = ValidationError(str(error))

    if hasattr(error, "message_dict"):
        for field_name, messages in error.message_dict.items():
            target = None if field_name == NON_FIELD_ERRORS else field_name
            if target not in form.fields:
                target = fallback_field if fallback_field in form.fields else None
            for message in messages:
                form.add_error(target, message)
        return

    target = fallback_field if fallback_field in form.fields else None
    for message in error.messages:
        form.add_error(target, message)
