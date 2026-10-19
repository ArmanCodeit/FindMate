import os
import re
import io
import logging
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import Config

logger = logging.getLogger(__name__)

_configured = False

def is_cloudinary_configured():
    """Check if Cloudinary has the necessary 3 credentials in environment or Config."""
    cloud_name = getattr(Config, "CLOUDINARY_CLOUD_NAME", None) or os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = getattr(Config, "CLOUDINARY_API_KEY", None) or os.getenv("CLOUDINARY_API_KEY")
    api_secret = getattr(Config, "CLOUDINARY_API_SECRET", None) or os.getenv("CLOUDINARY_API_SECRET")
    return bool(cloud_name and api_key and api_secret)

def configure_cloudinary():
    """Configure Cloudinary with existing environment credentials."""
    global _configured
    cloud_name = getattr(Config, "CLOUDINARY_CLOUD_NAME", None) or os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = getattr(Config, "CLOUDINARY_API_KEY", None) or os.getenv("CLOUDINARY_API_KEY")
    api_secret = getattr(Config, "CLOUDINARY_API_SECRET", None) or os.getenv("CLOUDINARY_API_SECRET")

    if not (cloud_name and api_key and api_secret):
        logger.error("Cloudinary credentials are not properly set in .env (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET).")
        return False

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    _configured = True
    return True

class CloudinaryService:
    """Service for uploading and managing assets in Cloudinary."""

    @staticmethod
    def upload_image(file_or_data, folder=None, public_id=None):
        """
        Uploads an image to Cloudinary.
        Supports:
        - Werkzeug FileStorage objects
        - Base64 data URIs (e.g., 'data:image/png;base64,...' from camera captures)
        - Raw bytes
        - File-like objects
        Returns Cloudinary response dict containing 'secure_url' and 'public_id'.
        """
        if not is_cloudinary_configured():
            raise ValueError("Cloudinary credentials are missing. Please check .env configuration.")

        configure_cloudinary()

        target_folder = folder or getattr(Config, "CLOUDINARY_FOLDER_ITEMS", "findmate/items")

        upload_options = {
            "folder": target_folder,
            "resource_type": "image",
            "unique_filename": True,
            "overwrite": False
        }
        if public_id:
            upload_options["public_id"] = public_id

        # Determine source
        upload_source = None
        if hasattr(file_or_data, "stream"):
            # Werkzeug FileStorage
            try:
                file_or_data.stream.seek(0)
            except Exception:
                pass
            upload_source = file_or_data.stream
        elif hasattr(file_or_data, "read") and callable(file_or_data.read):
            # File-like object
            try:
                file_or_data.seek(0)
            except Exception:
                pass
            upload_source = file_or_data
        elif isinstance(file_or_data, bytes):
            upload_source = io.BytesIO(file_or_data)
        elif isinstance(file_or_data, str):
            upload_source = file_or_data
        else:
            raise ValueError("Unsupported data source for Cloudinary upload.")

        try:
            result = cloudinary.uploader.upload(upload_source, **upload_options)
            secure_url = result.get("secure_url")
            pid = result.get("public_id")
            logger.info("Cloudinary upload successful: %s (public_id: %s)", secure_url, pid)
            return result
        except Exception as exc:
            logger.error("Cloudinary upload failed: %s", exc)
            raise ValueError(f"Cloudinary upload failed: {str(exc)}") from exc

    @staticmethod
    def extract_public_id(url_or_id):
        """Extract public_id from Cloudinary URL if a full URL is provided."""
        if not url_or_id or not isinstance(url_or_id, str):
            return None
        if not ("cloudinary.com" in url_or_id and "/image/upload/" in url_or_id):
            return url_or_id if ("/" in url_or_id or "_" in url_or_id) else None

        # Format: https://res.cloudinary.com/<cloud>/image/upload/(v<version>/)?<public_id>.<ext>
        match = re.search(r"/image/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$", url_or_id)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def delete_image(public_id):
        """Delete an asset from Cloudinary by its public_id."""
        if not public_id or not is_cloudinary_configured():
            return None
        try:
            configure_cloudinary()
            res = cloudinary.uploader.destroy(public_id)
            logger.info("Cloudinary delete result for %s: %s", public_id, res)
            return res
        except Exception as exc:
            logger.warning("Cloudinary delete failed for %s: %s", public_id, exc)
            return None

    @staticmethod
    def delete_image_by_url(url):
        """Extract public_id from Cloudinary URL and delete."""
        pid = CloudinaryService.extract_public_id(url)
        if pid:
            return CloudinaryService.delete_image(pid)
        return None
