from __future__ import annotations

import struct
import zlib

import pytest

from revit_mcp_server import image_check


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def png(raw=None, width=2, height=1, color=2, palette=None):
    if raw is None:
        raw = b"\x00\xff\xff\xff\x00\x00\x00"
    header = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    return (image_check.PNG_SIGNATURE + chunk(b"IHDR", header)
            + (chunk(b"PLTE", palette) if palette is not None else b"")
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_measured_content_and_blank():
    content = image_check.analyze_png_bytes(png())
    assert content["looks_blank"] is False
    assert content["content_fraction"] == 0.5
    blank = image_check.analyze_png_bytes(png(b"\x00" + b"\xff" * 6))
    assert blank["looks_blank"] is True


@pytest.mark.parametrize("blob", [
    png()[:-1],
    png()[:-12],
    png() + b"trailing",
    png(b"\x00\xff", width=2),
    png(b"\x00" + b"\xff" * 1_000_000, width=1),
    png(b"\x07" + b"\xff" * 6),
    png(b"\x00\x01", width=1, color=3, palette=b"\xff\xff\xff"),
    png(width=0),
    image_check.PNG_SIGNATURE + chunk(b"IDAT", b"x"),
])
def test_corrupt_images_never_claim_content(blob):
    result = image_check.analyze_png_bytes(blob)
    assert result["looks_blank"] is None
    assert result["analysis_error"]


def test_checksum_is_verified():
    blob = bytearray(png())
    blob[29] ^= 1
    assert "checksum" in image_check.analyze_png_bytes(bytes(blob))["analysis_error"]


def test_decompression_is_bounded_by_declared_pixels(monkeypatch):
    original = zlib.decompressobj
    limits = []

    class Decoder:
        def __init__(self):
            self.decoder = original()

        def decompress(self, data, max_length):
            limits.append(max_length)
            return self.decoder.decompress(data, max_length)

        def __getattr__(self, name):
            return getattr(self.decoder, name)

    monkeypatch.setattr(image_check.zlib, "decompressobj", Decoder)
    result = image_check.analyze_png_bytes(png(b"\x00" + b"x" * 1_000_000, width=1))
    assert limits == [5]  # one filter byte + one RGB pixel + overflow detection byte
    assert result["looks_blank"] is None


def test_file_read_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(image_check, "MAX_PNG_BYTES", 16)
    path = tmp_path / "large.png"
    path.write_bytes(b"x" * 100)
    result = image_check.analyze_png(path)
    assert result["bytes"] == 17
    assert result["analysis_error"]
