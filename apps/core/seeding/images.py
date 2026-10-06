"""Placeholder dish pictures so the frontend has visuals before real photos exist."""

import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

IMAGE_SIZE = (800, 600)
FONT_SIZE = 46
WRAP_WIDTH = 20
JPEG_QUALITY = 85


def placeholder_image(label, color):
    image = Image.new("RGB", IMAGE_SIZE, color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=FONT_SIZE)
    draw.multiline_text(
        (IMAGE_SIZE[0] // 2, IMAGE_SIZE[1] // 2),
        textwrap.fill(label, WRAP_WIDTH),
        fill="white",
        font=font,
        anchor="mm",
        align="center",
    )
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()