import io
from django.http import FileResponse
from PIL import Image

class CleanImageMiddleware:
    """
    Re-encode JPEG/PNG responses to ensure valid metadata
    so Flutter Web's ImageDecoder API can render them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only touch image responses
        content_type = response.get("Content-Type", "")
        if content_type in ["image/jpeg", "image/png"]:
            try:
                # Load bytes
                data = response.getvalue() if hasattr(response, "getvalue") else response.content
                img = Image.open(io.BytesIO(data))
                img = img.convert("RGB") if img.mode in ("RGBA", "P") else img

                # Re-save to memory buffer
                buf = io.BytesIO()
                fmt = "JPEG" if content_type == "image/jpeg" else "PNG"
                img.save(buf, fmt, quality=95, optimize=True)
                buf.seek(0)

                return FileResponse(buf, content_type=content_type)

            except Exception as e:
                # If Pillow fails, just return the original
                print("⚠️ Image cleanup failed:", e)
                return response

        return response
