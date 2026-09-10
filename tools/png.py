"""A minimal PNG reader/writer built only on the standard library.

The texture templates have to be generatable without Pillow or numpy so
that ``make textures`` works on a bare Python install, and Blender's own
bundled Python can call the same code.  Only what is actually needed is
implemented: 8-bit non-interlaced greyscale/RGB/RGBA.
"""

from __future__ import annotations

import struct
import zlib

_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, width, height, rows, channels=3, compress=6):
    """Write 8-bit PNG data.

    `rows` is a sequence of `height` byte buffers, each `width * channels`
    bytes long.  Rows are filtered with the Paeth predictor, which shrinks
    the flat colour fields in the texture templates dramatically.
    """
    colour_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    raw = bytearray()
    prev = bytes(width * channels)
    for y in range(height):
        row = bytes(rows[y])
        if len(row) != width * channels:
            raise ValueError(f"row {y} has {len(row)} bytes, "
                             f"expected {width * channels}")
        raw.append(4)                       # Paeth
        raw.extend(_paeth_filter(row, prev, channels))
        prev = row
    body = zlib.compress(bytes(raw), compress)
    header = struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(_chunk(b"IHDR", header))
        fh.write(_chunk(b"IDAT", body))
        fh.write(_chunk(b"IEND", b""))
    return path


def _paeth_filter(row, prev, bpp):
    out = bytearray(len(row))
    for i, cur in enumerate(row):
        a = row[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            pred = a
        elif pb <= pc:
            pred = b
        else:
            pred = c
        out[i] = (cur - pred) & 0xFF
    return out


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def read_png(path):
    """Decode an 8-bit non-interlaced PNG into rows of bytes."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    idat = bytearray()
    width = height = bitdepth = colour = 0
    palette = None
    while pos < len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bitdepth, colour, _, _, interlace = \
                struct.unpack(">IIBBBBB", chunk)
            if bitdepth != 8 or interlace:
                raise ValueError("only 8-bit non-interlaced PNGs are supported")
        elif tag == b"PLTE":
            palette = chunk
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break

    channels = _CHANNELS[colour]
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows = []
    prev = bytearray(stride)
    off = 0
    for _ in range(height):
        ftype = raw[off]
        line = bytearray(raw[off + 1:off + 1 + stride])
        off += 1 + stride
        _unfilter(ftype, line, prev, channels)
        rows.append(line)
        prev = line
    if colour == 3:
        if palette is None:
            raise ValueError("indexed PNG without a palette")
        expanded = []
        for line in rows:
            out = bytearray(width * 3)
            for x, idx in enumerate(line):
                out[x * 3:x * 3 + 3] = palette[idx * 3:idx * 3 + 3]
            expanded.append(out)
        rows, channels = expanded, 3
    return {"width": width, "height": height, "channels": channels,
            "rows": rows}


def _unfilter(ftype, line, prev, bpp):
    if ftype == 0:
        return
    n = len(line)
    if ftype == 1:
        for i in range(bpp, n):
            line[i] = (line[i] + line[i - bpp]) & 0xFF
    elif ftype == 2:
        for i in range(n):
            line[i] = (line[i] + prev[i]) & 0xFF
    elif ftype == 3:
        for i in range(n):
            a = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
    elif ftype == 4:
        for i in range(n):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            if pa <= pb and pa <= pc:
                pred = a
            elif pb <= pc:
                pred = b
            else:
                pred = c
            line[i] = (line[i] + pred) & 0xFF
    else:
        raise ValueError(f"unknown PNG filter {ftype}")
