"""Decode a bounded raster and strip metadata/trailing payloads before publishing."""
import io
from PIL import Image, UnidentifiedImageError


def sanitize_avatar(content):
    if not content or len(content) > 2 * 1024 * 1024:
        raise ValueError('图片不超过 2MB。')
    try:
        with Image.open(io.BytesIO(content), formats=('JPEG','PNG','GIF','WEBP')) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError('图片像素过大，请缩小到 400 万像素以内。')
            source.seek(0)
            source.load()
            image = source.convert('RGBA')
            image.thumbnail((512,512))
            output = io.BytesIO()
            # A fresh image avoids copying EXIF, comments or ICC metadata.
            clean = Image.new('RGBA',image.size)
            clean.paste(image)
            clean.save(output,format='PNG')
            return output.getvalue()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise ValueError('图片无法读取，请重新选择 PNG/JPG/GIF/WEBP 图片。') from error
