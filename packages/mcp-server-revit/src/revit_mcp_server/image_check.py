"""Look inside a rendered PNG without any imaging library: size, a colour histogram, and a "looks blank" flag.

Used by ``revit_render_check``. A Revit export can succeed (the file exists, it has bytes) and still show nothing:
an empty 3D view, a crop box that misses the model, a view that was never regenerated. A person notices that when
they open the picture. This module lets the tool say so first.

Only what Revit writes is decoded: non-interlaced PNG, 8 bit per channel, grayscale / RGB / palette / with alpha.
Anything else comes back with ``looks_blank: None`` and a reason, never a guess.
"""
from __future__ import annotations

import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PIXELS = 12_000_000  # beyond this the pure Python pass would take too long; report instead of guessing
MAX_PNG_BYTES = 64_000_000
BLANK_DOMINANT_FRACTION = 0.995  # this share of pixels in one colour (5 bits per channel) means "blank"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _unfilter(data: bytes, width: int, height: int, bpp: int) -> List[bytearray]:
    stride = width * bpp
    rows: List[bytearray] = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = data[pos]
        raw = bytearray(data[pos + 1 : pos + 1 + stride])
        pos += 1 + stride
        if ftype == 0:
            cur = raw
        elif ftype == 1:  # Sub
            cur = raw
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 255
        elif ftype == 2:  # Up
            cur = bytearray((a + b) & 255 for a, b in zip(raw, prev))
        elif ftype == 3:  # Average
            cur = raw
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:  # Paeth
            cur = raw
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (cur[i] + pred) & 255
        else:
            raise ValueError(f"unknown PNG filter type {ftype}")
        rows.append(cur)
        prev = cur
    return rows


def analyze_png_bytes(blob: bytes) -> Dict[str, Any]:
    """Facts about a PNG held in memory. Never raises: problems are reported in ``analysis_error``."""
    result: Dict[str, Any] = {
        "width": None,
        "height": None,
        "looks_blank": None,
        "dominant_fraction": None,
        "content_fraction": None,
        "distinct_colors": None,
        "luminance_histogram": None,
        "analysis_error": None,
    }
    try:
        if len(blob) > MAX_PNG_BYTES:
            raise ValueError("PNG file exceeds the analysis byte limit")
        if not blob.startswith(PNG_SIGNATURE):
            result["analysis_error"] = "not a PNG file (bad signature)"
            return result
        pos = len(PNG_SIGNATURE)
        ihdr: Optional[tuple] = None
        palette = b""
        idat = bytearray()
        ended = False
        idat_ended = False
        while pos + 8 <= len(blob):
            length, ctype = struct.unpack(">I4s", blob[pos : pos + 8])
            if not all(65 <= b <= 90 or 97 <= b <= 122 for b in ctype) or not 65 <= ctype[2] <= 90:
                raise ValueError("invalid PNG chunk type")
            if pos + 12 + length > len(blob):
                raise ValueError("truncated PNG chunk")
            body = blob[pos + 8 : pos + 8 + length]
            checksum = struct.unpack(">I", blob[pos + 8 + length : pos + 12 + length])[0]
            if zlib.crc32(ctype + body) & 0xFFFFFFFF != checksum:
                raise ValueError("PNG chunk checksum mismatch")
            if ihdr is None and ctype != b"IHDR":
                raise ValueError("IHDR must be the first PNG chunk")
            pos += 12 + length
            if ctype == b"IHDR":
                if ihdr is not None or length != 13:
                    raise ValueError("invalid or duplicate IHDR chunk")
                ihdr = struct.unpack(">IIBBBBB", body)
            elif ctype == b"PLTE":
                if palette or idat or not length or length > 768 or length % 3:
                    raise ValueError("invalid PNG palette")
                palette = bytes(body)
            elif ctype == b"IDAT":
                if idat_ended:
                    raise ValueError("PNG IDAT chunks must be consecutive")
                idat += body
            elif ctype == b"IEND":
                if length != 0 or pos != len(blob):
                    raise ValueError("invalid PNG end chunk or trailing data")
                ended = True
                break
            elif ctype[0] & 32 == 0:
                raise ValueError("unknown critical PNG chunk")
            if ctype != b"IDAT" and idat:
                idat_ended = True
        if ihdr is None:
            result["analysis_error"] = "PNG has no IHDR chunk"
            return result
        if not ended or not idat:
            raise ValueError("PNG is missing image data or its end chunk")
        width, height, depth, ctype_id, comp, filt, interlace = ihdr
        result["width"], result["height"] = width, height
        if not width or not height or comp != 0 or filt != 0:
            raise ValueError("invalid PNG dimensions or compression/filter method")
        if depth != 8 or ctype_id not in _CHANNELS or interlace != 0:
            result["analysis_error"] = (
                f"unsupported PNG layout (bit depth {depth}, colour type {ctype_id}, interlace {interlace}); "
                "only 8-bit non-interlaced PNG is analysed"
            )
            return result
        if width * height > MAX_PIXELS:
            result["analysis_error"] = f"image is {width}x{height}; export a smaller width to analyse it"
            return result
        channels = _CHANNELS[ctype_id]
        if ctype_id == 3 and not palette:
            raise ValueError("indexed PNG has no palette")
        expected = height * (1 + width * channels)
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(idat), expected + 1)
        if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("PNG image data does not match its declared dimensions")
        rows = _unfilter(pixels, width, height, channels)

        quantized: Counter = Counter()
        lum_bins = [0] * 8
        tables = None
        if ctype_id == 3:
            padded = palette + bytes(768 - len(palette)) if len(palette) < 768 else palette
            tables = (bytes(padded[0:768:3]), bytes(padded[1:768:3]), bytes(padded[2:768:3]))
        for row in rows:
            if tables is not None:
                if any(v >= len(palette) // 3 for v in row):
                    raise ValueError("PNG pixel references a missing palette entry")
                rs, gs, bs = row.translate(tables[0]), row.translate(tables[1]), row.translate(tables[2])
            elif ctype_id in (0, 4):
                rs = gs = bs = row[0::channels]
            else:
                rs, gs, bs = row[0::channels], row[1::channels], row[2::channels]
            quantized.update(zip((v >> 3 for v in rs), (v >> 3 for v in gs), (v >> 3 for v in bs)))
            for lum, n in Counter((299 * x + 587 * y + 114 * z) // 1000 >> 5 for x, y, z in zip(rs[::4], gs[::4], bs[::4])).items():
                lum_bins[min(lum, 7)] += n
        total = width * height
        dominant = quantized.most_common(1)[0][1] / total if total else 1.0
        sampled = sum(lum_bins) or 1
        result.update(
            looks_blank=dominant >= BLANK_DOMINANT_FRACTION,
            dominant_fraction=round(dominant, 5),
            content_fraction=round(1.0 - dominant, 5),
            distinct_colors=sum(1 for n in quantized.values() if n / total >= 0.001),
            luminance_histogram=[round(n / sampled, 4) for n in lum_bins],
        )
    except Exception as exc:  # noqa: BLE001 - a bad file must be reported, not raised
        result["analysis_error"] = f"{type(exc).__name__}: {exc}"
        result["looks_blank"] = None
    return result


def analyze_png(path: Path) -> Dict[str, Any]:
    """``analyze_png_bytes`` for a file, plus its size in bytes."""
    with Path(path).open("rb") as source:
        blob = source.read(MAX_PNG_BYTES + 1)
    out = analyze_png_bytes(blob)
    out["bytes"] = len(blob)
    return out
