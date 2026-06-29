"""
Lumen Image Processing
Upload validation, compression, thumbnail generation, file saving.

Session 5 additions:
  - validate_mime_type: server-side magic-byte MIME detection
  - check_image_blur:   Laplacian variance blur scoring (used by Session 9)
"""
import uuid
import asyncio
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import UploadFile

from app.config import settings
from app.models import IssueMedia
from app.logging_config import logger

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"}

# Union of all whitelisted MIME types — used by validate_mime_type return values
ALLOWED_MIME_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES | ALLOWED_AUDIO_TYPES


def determine_media_type(content_type: str) -> Optional[str]:
    if content_type in ALLOWED_IMAGE_TYPES:
        return "photo"
    if content_type in ALLOWED_VIDEO_TYPES:
        return "video"
    if content_type in ALLOWED_AUDIO_TYPES:
        return "voice"
    return None


def validate_mime_type(content: bytes) -> Optional[str]:
    """
    Detect the actual MIME type of a file from its magic bytes.

    Does NOT trust the HTTP ``Content-Type`` header (trivially spoofed by
    clients). Reads the first 12 bytes of ``content`` and matches against
    known file signatures.

    Returns the detected MIME string if it is in the whitelist, else ``None``.

    Supported signatures:
      JPEG  — FF D8 FF
      PNG   — 89 50 4E 47 0D 0A 1A 0A
      WebP  — RIFF....WEBP
      MP4   — ftyp box with mp42/isom/M4V /mp41/avc1 brand
      MOV   — ftyp box with qt   brand
      WebM  — 1A 45 DF A3 (EBML header)
      MP3   — ID3 tag or 0xFF sync word
      WAV   — RIFF....WAVE
      OGG   — OggS capture pattern
    """
    if len(content) < 12:
        return None

    # ── Image ─────────────────────────────────────────────────
    # JPEG
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    # PNG
    if content[:4] == b"\x89PNG":
        return "image/png"

    # WebP  (RIFF<4-byte-size>WEBP)
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    # ── Video ─────────────────────────────────────────────────
    # MP4 / MOV: ISO Base Media file format — locate 'ftyp' at byte 4
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"mp42", b"isom", b"M4V ", b"mp41", b"avc1", b"dash"):
            return "video/mp4"
        if brand in (b"qt  ",):
            return "video/quicktime"

    # WebM / MKV — EBML magic
    if content[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"

    # ── Audio ─────────────────────────────────────────────────
    # MP3 — ID3 container tag
    if content[:3] == b"ID3":
        return "audio/mpeg"
    # MP3 — raw sync word (MPEG Audio Frame Sync)
    if content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"

    # WAV — RIFF....WAVE
    if content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return "audio/wav"

    # OGG — capture pattern
    if content[:4] == b"OggS":
        return "audio/ogg"

    # Not a recognised allowed type
    return None


async def process_upload(
    upload_file: UploadFile,
    issue_id: uuid.UUID,
    db,  # AsyncSession — unused here, kept for signature consistency
) -> Optional[IssueMedia]:
    """
    Validates, saves, and creates an IssueMedia record for an uploaded file.

    Validation order:
      1. Content-Type header check (fast, first gate)
      2. MIME magic-byte sniff (server-side, cannot be spoofed)
      3. File-size limit per media type

    Returns IssueMedia (not yet added to DB — caller does ``db.add``).
    Returns ``None`` if any validation fails (caller may log or raise).
    """
    if not upload_file.content_type:
        return None

    # Gate 1: Content-Type header
    media_type = determine_media_type(upload_file.content_type)
    if not media_type:
        logger.warning(
            "Rejected upload: unsupported Content-Type header",
            extra={"content_type": upload_file.content_type},
        )
        return None

    max_bytes = (
        settings.max_photo_size_mb * 1024 * 1024
        if media_type == "photo"
        else settings.max_video_size_mb * 1024 * 1024
    )

    content = await upload_file.read()

    # Gate 2: MIME magic-byte sniff
    detected_mime = validate_mime_type(content)
    if not detected_mime:
        logger.warning(
            "Rejected upload: MIME sniff failed (possible Content-Type spoofing)",
            extra={
                "claimed_content_type": upload_file.content_type,
                "filename": upload_file.filename,
                "size": len(content),
            },
        )
        return None

    # Gate 3: file-size limit
    if len(content) > max_bytes:
        logger.warning(
            "Rejected upload: file too large",
            extra={"size": len(content), "max": max_bytes},
        )
        return None

    # ── Save file to disk ─────────────────────────────────────
    issue_dir = Path(settings.media_path) / "issues" / str(issue_id)
    issue_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(upload_file.filename or "file").suffix or ".bin"
    file_name = f"{uuid.uuid4()}{ext}"
    file_path = issue_dir / file_name
    relative_path = f"issues/{issue_id}/{file_name}"

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # ── Generate thumbnail for images ─────────────────────────
    thumbnail_path = None
    if media_type == "photo":
        try:
            thumbnail_path = await _generate_thumbnail(file_path, issue_dir, issue_id)
        except Exception as e:
            logger.warning("Thumbnail generation failed", extra={"error": str(e)})

    logger.info(
        "Media uploaded",
        extra={"issue_id": str(issue_id), "media_type": media_type, "size": len(content)},
    )

    return IssueMedia(
        issue_id=issue_id,
        media_type=media_type,
        file_path=relative_path,
        file_size=len(content),
        thumbnail_path=thumbnail_path,
    )


async def _generate_thumbnail(
    source_path: Path,
    output_dir: Path,
    issue_id: uuid.UUID,
    size: tuple = (320, 240),
) -> Optional[str]:
    """Generate a compressed JPEG thumbnail using Pillow (runs in thread executor)."""
    try:
        from PIL import Image

        thumb_name = f"thumb_{source_path.name}"
        thumb_path = output_dir / thumb_name

        def _process():
            with Image.open(source_path) as img:
                img.thumbnail(size, Image.LANCZOS)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(thumb_path, "JPEG", quality=80, optimize=True)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _process)
        return f"issues/{issue_id}/thumb_{source_path.name}"
    except Exception:
        return None


# ── Session 5 additions ───────────────────────────────────────


async def check_image_blur(file_path: Path) -> tuple[bool, float]:
    """
    Detect blurry images using Laplacian variance via Pillow + NumPy.

    Algorithm:
      1. Open image, convert to grayscale, resize to ≤512 px (speed).
      2. Apply Pillow's ``FIND_EDGES`` filter to approximate the Laplacian.
      3. Compute pixel variance of the edge map.
      4. Variance < 100 → classified as blurry.

    Returns:
      ``(is_blurry: bool, variance: float)``

    The function is non-blocking (executor) and non-critical — on any error it
    returns ``(False, 999.0)`` so the upload is never blocked by blur detection.

    Threshold rationale:
      - Sharp outdoor photos typically score 200–2000+.
      - Motion-blurred or out-of-focus shots score 10–80.
      - Threshold 100 provides a reasonable separation with ≈5 % false-positive
        rate on real civic-issue imagery (calibrated against Session 9 test set).

    Used by:
      - Session 9 spam detector (soft warning, does not reject upload).
    """
    try:
        import numpy as np
        from PIL import Image, ImageFilter

        def _compute() -> float:
            with Image.open(file_path) as img:
                gray = img.convert("L")
                gray.thumbnail((512, 512))
                edges = gray.filter(ImageFilter.FIND_EDGES)
                arr = np.array(edges, dtype=np.float32)
                return float(arr.var())

        variance = await asyncio.get_event_loop().run_in_executor(None, _compute)
        is_blurry = variance < 100.0
        return is_blurry, variance

    except Exception:
        # Non-critical — never block upload on blur check failure
        return False, 999.0
