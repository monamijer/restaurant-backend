from django.utils.text import slugify

FALLBACK_SLUG = "item"


def unique_slug(model, source, *, instance_pk=None, field="slug"):
    """Slugify `source` and append -2, -3... until no other row uses it."""
    base = slugify(source) or FALLBACK_SLUG
    queryset = model.objects.exclude(pk=instance_pk) if instance_pk else model.objects.all()
    candidate, suffix = base, 1
    while queryset.filter(**{field: candidate}).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate