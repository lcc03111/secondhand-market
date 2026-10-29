from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def save_upload(file_storage, upload_folder):
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("仅支持 PNG、JPG、JPEG、WEBP 或 GIF 图片。")
    filename = f"{uuid4().hex}{suffix}"
    file_storage.save(Path(upload_folder) / filename)
    return filename
