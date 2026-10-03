"""Upload validation shared by every serializer that accepts an image."""

from rest_framework import serializers

MAX_IMAGE_MB = 2
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")


def validate_uploaded_image(upload):
    """Check size and the real format as decoded by Pillow, never the filename or MIME type."""
    if upload is None:
        return upload
    if upload.size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError(f"Image must not exceed {MAX_IMAGE_MB} MB.")
    detected_format = getattr(getattr(upload, "image", None), "format", None)
    if detected_format not in ALLOWED_IMAGE_FORMATS:
        raise serializers.ValidationError("Only JPEG, PNG or WebP images are accepted.")
    return upload