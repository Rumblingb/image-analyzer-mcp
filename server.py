#!/usr/bin/env python3
"""
Image Analyzer MCP Server

An MCP server that provides image analysis tools using Pillow (PIL).
No external APIs required. All processing is done locally.

Tools:
  - analyze_image        : Analyze image file (dimensions, format, mode, size, aspect ratio, DPI)
  - analyze_image_base64 : Analyze image from base64-encoded data
  - get_dominant_colors  : Extract dominant colors with hex values
  - get_image_metadata   : Extract EXIF metadata (GPS, camera info, date taken, etc.)
  - convert_image        : Convert between PNG/JPEG/WEBP/GIF formats (returns base64)
"""

import base64
import io
import math
import os
import struct
import sys
from collections import Counter
from typing import Optional

from mcp.server import Server, stdio_server
from mcp.types import Tool, TextContent, ImageContent
from PIL import Image, ImageOps


server = Server("image-analyzer")


def _get_image_from_path(image_path: str) -> Image.Image:
    """Open an image from a file path. Supports local paths and /mnt/c/ Windows paths."""
    expanded = os.path.expanduser(image_path)
    if not os.path.exists(expanded):
        raise FileNotFoundError(f"Image not found: {image_path}")
    return Image.open(expanded)


def _get_image_from_base64(b64_data: str) -> Image.Image:
    """Open an image from a base64-encoded string."""
    raw = base64.b64decode(b64_data)
    buf = io.BytesIO(raw)
    return Image.open(buf)


def _image_to_base64(img: Image.Image, fmt: str, quality: int = 85) -> str:
    """Convert a PIL Image to a base64-encoded string."""
    buf = io.BytesIO()
    save_kwargs = {}
    if fmt.upper() in ("JPEG", "JPG"):
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif fmt.upper() == "WEBP":
        save_kwargs["quality"] = quality
    elif fmt.upper() == "PNG":
        save_kwargs["optimize"] = True
    img.save(buf, format=fmt, **save_kwargs)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _format_pixels(w: int, h: int) -> str:
    """Return a human-readable pixel count."""
    total = w * h
    if total >= 1_000_000:
        return f"{total / 1_000_000:.2f} MP"
    elif total >= 1_000:
        return f"{total / 1_000:.1f} KP"
    return str(total)


def _get_file_size(path: str) -> tuple[int, str]:
    """Get file size in bytes and human-readable form."""
    size = os.path.getsize(path)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return size, f"{size:.1f} {unit}"
        size /= 1024
    return os.path.getsize(path), f"{size:.1f} GB"


def _format_gps_coords(gps_data: dict) -> Optional[str]:
    """Convert raw GPS EXIF data to a human-readable coordinate string."""
    try:
        def _to_decimal(frac_tuple):
            d, m, s = frac_tuple
            return d + m / 60.0 + s / 3600.0

        lat_ref = gps_data.get(1, b"N")  # GPSLatitudeRef
        lat_vals = gps_data.get(2)       # GPSLatitude
        lon_ref = gps_data.get(3, b"E")  # GPSLongitudeRef
        lon_vals = gps_data.get(4)       # GPSLongitude

        if lat_vals is None or lon_vals is None:
            return None

        lat = _to_decimal(lat_vals)
        lon = _to_decimal(lon_vals)

        if isinstance(lat_ref, bytes):
            lat_ref = lat_ref.decode()
        if isinstance(lon_ref, bytes):
            lon_ref = lon_ref.decode()

        if lat_ref.upper() == "S":
            lat = -lat
        if lon_ref.upper() == "W":
            lon = -lon

        return f"{lat:.6f}, {lon:.6f}"
    except (TypeError, ValueError, ZeroDivisionError, KeyError, IndexError):
        return None


def _get_exif_dict(img: Image.Image) -> dict:
    """Extract well-known EXIF tags into a readable dictionary."""
    info = {}
    exif = img.getexif()
    if not exif:
        return info

    # Tag name mapping for common EXIF tags
    TAG_NAMES = {
        0x010F: "make",             # Make
        0x0110: "model",            # Model
        0x0112: "orientation",       # Orientation
        0x0131: "software",         # Software
        0x0132: "date_time",        # DateTime
        0x013E: "white_balance",    # WhiteBalance
        0x0213: "ycbc_pos",         # YCbCrPositioning
        0x8298: "copyright",        # Copyright
        0x8769: "exif_offset",      # ExifOffset
        0x8822: "exposure_program", # ExposureProgram
        0x8827: "iso",              # ISOSpeedRatings
        0x9000: "exif_version",     # ExifVersion
        0x9003: "date_taken",       # DateTimeOriginal
        0x9004: "date_digitized",   # DateTimeDigitized
        0x9101: "component_config", # ComponentsConfiguration
        0x9102: "compressed_bpp",   # CompressedBitsPerPixel
        0x9201: "shutter_speed",    # ShutterSpeedValue
        0x9202: "aperture",         # ApertureValue
        0x9203: "brightness",       # BrightnessValue
        0x9204: "exposure_bias",    # ExposureBiasValue
        0x9205: "max_aperture",     # MaxApertureValue
        0x9206: "subject_dist",     # SubjectDistance
        0x9207: "metering_mode",    # MeteringMode
        0x9208: "light_source",     # LightSource
        0x9209: "flash",            # Flash
        0x920A: "focal_length",     # FocalLength
        0x927C: "maker_note",       # MakerNote
        0x9286: "user_comment",     # UserComment
        0x9290: "subsec_time",      # SubsecTime
        0x9291: "subsec_orig",      # SubsecTimeOriginal
        0x9292: "subsec_digit",     # SubsecTimeDigitized
        0xA000: "flashpix_version", # FlashpixVersion
        0xA001: "color_space",      # ColorSpace
        0xA002: "pixel_dimensions", # PixelXDimension / PixelYDimension
        0xA003: "pixel_dimensions_y",
        0xA20E: "focal_plane_xres", # FocalPlaneXResolution
        0xA20F: "focal_plane_yres", # FocalPlaneYResolution
        0xA210: "focal_plane_unit", # FocalPlaneResolutionUnit
        0xA401: "custom_rendered",  # CustomRendered
        0xA402: "exposure_mode",    # ExposureMode
        0xA403: "white_balance_mode", # WhiteBalanceMode
        0xA404: "digital_zoom",     # DigitalZoomRatio
        0xA405: "focal_len_35mm",   # FocalLengthIn35mmFilm
        0xA406: "scene_capture",    # SceneCaptureType
        0xA407: "gain_control",     # GainControl
        0xA408: "contrast",         # Contrast
        0xA409: "saturation",       # Saturation
        0xA40A: "sharpness",        # Sharpness
        0xA40B: "device_setting",   # DeviceSettingDescription
        0xA40C: "subject_dist_range", # SubjectDistanceRange
        0xA420: "image_unique_id",  # ImageUniqueID
    }

    # Orientation descriptions
    ORIENTATIONS = {
        1: "Normal",
        2: "Mirrored horizontally",
        3: "Rotated 180°",
        4: "Mirrored vertically",
        5: "Mirrored horizontally & rotated 270° CW",
        6: "Rotated 90° CW",
        7: "Mirrored horizontally & rotated 90° CW",
        8: "Rotated 270° CW",
    }

    for tag_id, tag_name in TAG_NAMES.items():
        try:
            val = exif.get(tag_id)
            if val is not None:
                if isinstance(val, bytes):
                    try:
                        info[tag_name] = val.decode("utf-8", errors="replace").strip("\x00")
                    except UnicodeDecodeError:
                        info[tag_name] = repr(val)
                elif isinstance(val, tuple) and tag_name == "pixel_dimensions":
                    info["x_resolution"] = val[0] if len(val) > 0 else None
                    info["y_resolution"] = val[1] if len(val) > 1 else None
                elif tag_name == "orientation":
                    info[tag_name] = ORIENTATIONS.get(val, str(val))
                else:
                    info[tag_name] = val
        except Exception:
            pass

    # Try to extract GPS info from IFD
    gps_ifd = exif.get_ifd(0x8825)  # GPSInfo IFD
    if gps_ifd:
        coords = _format_gps_coords(gps_ifd)
        if coords:
            info["gps_coordinates"] = coords

        gps_tag_map = {
            0: "gps_version",
            5: "gps_dest_lat_ref",
            6: "gps_dest_lat",
            7: "gps_dest_lon_ref",
            8: "gps_dest_lon",
            29: "gps_datestamp",
        }
        for tag_id, tag_name in gps_tag_map.items():
            try:
                val = gps_ifd.get(tag_id)
                if val is not None:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace").strip("\x00")
                    info[tag_name] = val
            except Exception:
                pass

    return info


# ---------------------------------------------------------------------------
# MCP Tool Implementations
# ---------------------------------------------------------------------------

async def handle_analyze_image(image_path: str) -> list:
    """Analyze an image file and return dimensions, format, mode, size, aspect ratio, DPI."""
    img = _get_image_from_path(image_path)
    w, h = img.size
    fmt = img.format or "Unknown"
    mode = img.mode
    raw_size, human_size = _get_file_size(image_path)
    aspect = f"{w / h:.4f}" if h != 0 else "∞"
    dpi = img.info.get("dpi", (0, 0))

    result = {
        "file": os.path.abspath(image_path),
        "dimensions": {"width": w, "height": h, "pixels": _format_pixels(w, h)},
        "format": fmt,
        "mode": mode,
        "file_size": {"bytes": raw_size, "human": human_size},
        "aspect_ratio": {"decimal": float(aspect), "fraction": f"{w}:{h}"},
        "dpi": {"x": float(dpi[0]), "y": float(dpi[1])} if dpi != (0, 0) else None,
    }

    return [TextContent(type="text", text=str(result))]


async def handle_analyze_image_base64(base64_data: str) -> list:
    """Analyze an image from base64-encoded data."""
    img = _get_image_from_base64(base64_data)
    w, h = img.size
    fmt = img.format or "Unknown"
    mode = img.mode
    raw_size = len(base64.b64decode(base64_data))
    aspect = f"{w / h:.4f}" if h != 0 else "∞"
    dpi = img.info.get("dpi", (0, 0))

    for unit in ("B", "KB", "MB"):
        if raw_size < 1024:
            human_size = f"{raw_size:.1f} {unit}"
            break
        raw_size_f = raw_size / 1024
    else:
        human_size = f"{raw_size_f:.1f} GB"

    result = {
        "source": "base64",
        "dimensions": {"width": w, "height": h, "pixels": _format_pixels(w, h)},
        "format": fmt,
        "mode": mode,
        "file_size": {"bytes": len(base64.b64decode(base64_data)), "human": human_size},
        "aspect_ratio": {"decimal": float(aspect), "fraction": f"{w}:{h}"},
        "dpi": {"x": float(dpi[0]), "y": float(dpi[1])} if dpi != (0, 0) else None,
    }

    return [TextContent(type="text", text=str(result))]


async def handle_get_dominant_colors(image_path: str, count: int = 5) -> list:
    """Extract dominant colors from an image.

    Uses color quantization to reduce the image to N clusters and returns
    hex values for each dominant color along with an approximate percentage.
    """
    if count < 1:
        count = 1
    if count > 128:
        count = 128

    img = _get_image_from_path(image_path)

    # Ensure RGB mode
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize for performance (max 256x256 thumb)
    img.thumbnail((256, 256), Image.LANCZOS)

    # Get raw pixel data
    pixels = list(img.getdata())

    # Use quantization via reduce palette for smaller images
    # For more accuracy, sample massively
    sampled = pixels[::4]  # take every 4th pixel for speed
    if len(sampled) < count * 10:
        sampled = pixels[::2]
    if len(sampled) < count * 10:
        sampled = pixels

    # Cluster colors by rounding to nearest color cube
    # Quantize to 8-bit per channel → 32 values per channel
    bucket_size = 8
    buckets: dict[tuple, list] = {}
    for r, g, b in sampled:
        bucket = (r // bucket_size * bucket_size,
                  g // bucket_size * bucket_size,
                  b // bucket_size * bucket_size)
        buckets.setdefault(bucket, []).append((r, g, b))

    # Sort buckets by size (descending)
    sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)

    # Take top N buckets
    top_buckets = sorted_buckets[:count]

    total_pixels = len(sampled)
    colors = []
    for (br, bg, bb), pixel_list in top_buckets:
        # Average the colors in this bucket for more accurate representation
        avg_r = sum(p[0] for p in pixel_list) // len(pixel_list)
        avg_g = sum(p[1] for p in pixel_list) // len(pixel_list)
        avg_b = sum(p[2] for p in pixel_list) // len(pixel_list)
        percentage = round(len(pixel_list) / total_pixels * 100, 2)
        hex_val = f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}"
        colors.append({
            "hex": hex_val,
            "rgb": {"r": avg_r, "g": avg_g, "b": avg_b},
            "percentage": percentage,
        })

    result = {
        "file": os.path.abspath(image_path),
        "dominant_colors": colors,
        "total_colors_extracted": len(colors),
    }

    return [TextContent(type="text", text=str(result))]


async def handle_get_image_metadata(image_path: str) -> list:
    """Extract EXIF metadata from an image, including GPS, camera info, and dates."""
    img = _get_image_from_path(image_path)
    exif_data = _get_exif_dict(img)

    # Also grab basic info not stored in EXIF
    w, h = img.size
    fmt = img.format or "Unknown"

    result = {
        "file": os.path.abspath(image_path),
        "basic": {
            "format": fmt,
            "dimensions": {"width": w, "height": h},
            "mode": img.mode,
        },
        "exif": exif_data,
        "has_exif": len(exif_data) > 0,
    }

    return [TextContent(type="text", text=str(result))]


async def handle_convert_image(
    image_path: str,
    target_format: str,
    quality: int = 85,
) -> list:
    """Convert an image to a different format and return base64-encoded result.

    Supported target formats: PNG, JPEG, WEBP, GIF.
    """
    target_format = target_format.upper().replace("JPG", "JPEG")
    valid_formats = {"PNG", "JPEG", "WEBP", "GIF"}
    if target_format not in valid_formats:
        raise ValueError(
            f"Unsupported target format: {target_format}. "
            f"Supported formats: {', '.join(sorted(valid_formats))}"
        )

    if quality < 1:
        quality = 1
    if quality > 100:
        quality = 100

    img = _get_image_from_path(image_path)
    original_format = img.format or "Unknown"

    # Handle mode conversions for formats that don't support certain modes
    if target_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif target_format == "GIF" and img.mode != "P":
        img = img.convert("P", palette=Image.Palette.ADAPTIVE)

    b64 = _image_to_base64(img, target_format, quality=quality)

    result = {
        "file": os.path.abspath(image_path),
        "original_format": original_format,
        "target_format": target_format,
        "quality": quality,
        "base64": b64,
    }

    return [TextContent(type="text", text=str(result))]


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_image",
            description=(
                "Analyze an image file and return its dimensions, format, color mode, "
                "file size, aspect ratio, and DPI."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file",
                    },
                },
                "required": ["image_path"],
            },
        ),
        Tool(
            name="analyze_image_base64",
            description=(
                "Analyze an image from a base64-encoded string and return its dimensions, "
                "format, color mode, file size, aspect ratio, and DPI."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "base64_data": {
                        "type": "string",
                        "description": "Base64-encoded image data",
                    },
                },
                "required": ["base64_data"],
            },
        ),
        Tool(
            name="get_dominant_colors",
            description=(
                "Extract the dominant colors from an image. Returns each color's hex value, "
                "RGB components, and approximate percentage of the image it occupies."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of dominant colors to extract (default: 5, max: 128)",
                        "default": 5,
                    },
                },
                "required": ["image_path"],
            },
        ),
        Tool(
            name="get_image_metadata",
            description=(
                "Extract EXIF metadata from an image, including GPS coordinates, camera "
                "make/model, date taken, orientation, and other embedded metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file",
                    },
                },
                "required": ["image_path"],
            },
        ),
        Tool(
            name="convert_image",
            description=(
                "Convert an image to a different format (PNG, JPEG, WEBP, GIF) and return "
                "the result as a base64-encoded string. Optionally adjust output quality (1-100)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file",
                    },
                    "target_format": {
                        "type": "string",
                        "description": "Target format: PNG, JPEG, WEBP, or GIF",
                    },
                    "quality": {
                        "type": "integer",
                        "description": "Output quality (1-100, default: 85). Used for JPEG and WEBP.",
                        "default": 85,
                    },
                },
                "required": ["image_path", "target_format"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    if name == "analyze_image":
        return await handle_analyze_image(arguments["image_path"])
    elif name == "analyze_image_base64":
        return await handle_analyze_image_base64(arguments["base64_data"])
    elif name == "get_dominant_colors":
        return await handle_get_dominant_colors(
            arguments["image_path"],
            arguments.get("count", 5),
        )
    elif name == "get_image_metadata":
        return await handle_get_image_metadata(arguments["image_path"])
    elif name == "convert_image":
        return await handle_convert_image(
            arguments["image_path"],
            arguments["target_format"],
            arguments.get("quality", 85),
        )
    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Image Analyzer MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind SSE server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE server (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as streams:
                await server.run(
                    streams[0],
                    streams[1],
                    server.create_initialization_options(),
                )

        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
            ],
        )

        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        async def _run():
            async with stdio_server() as streams:
                await server.run(
                    streams[0],
                    streams[1],
                    server.create_initialization_options(),
                )

        import asyncio
        asyncio.run(_run())


if __name__ == "__main__":
    main()
