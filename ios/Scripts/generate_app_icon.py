#!/usr/bin/env python3
"""Generate DevLoop's dependency-free 1024px app icon.

The icon is intentionally geometric so this script remains the editable source of
truth. It writes a standards-compliant RGBA PNG using only Python's stdlib.
"""
from pathlib import Path
import math
import struct
import zlib

SIZE = 1024
OUT = Path(__file__).parents[1] / "DevLoop/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png"


def pixel(x: int, y: int) -> tuple[int, int, int, int]:
    # Quiet graphite radial field.
    d = math.hypot(x - 512, y - 480) / 724
    glow = max(0.0, 1.0 - d) * 13
    r, g, b = 8 + glow * .35, 11 + glow * .55, 12 + glow * .60

    # Three offset concentric progress arcs, echoing Time/Output/Consistency.
    cx, cy = 512, 500
    radius = math.hypot(x - cx, y - cy)
    angle = (math.atan2(y - cy, x - cx) + math.pi / 2) % (2 * math.pi)
    rings = ((292, .82, (184, 245, 51)), (225, .71, (59, 217, 151)), (158, .61, (59, 184, 222)))
    for rad, progress, color in rings:
        dist = abs(radius - rad)
        if dist <= 25:
            if angle <= progress * 2 * math.pi:
                edge = min(1.0, (26 - dist) / 5)
                mix = max(.15, edge)
                r, g, b = [base * (1 - mix) + accent * mix for base, accent in zip((r, g, b), color)]
            else:
                r, g, b = [c + 13 for c in (r, g, b)]

    # Calm center mark.
    if radius < 54:
        blend = max(0.0, min(1.0, (58 - radius) / 8))
        r, g, b = r * (1-blend) + 184*blend, g * (1-blend) + 245*blend, b * (1-blend) + 51*blend
    rgb = [max(0, min(255, int(v))) for v in (r, g, b)]
    return rgb[0], rgb[1], rgb[2], 255


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def main() -> None:
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)  # PNG filter: none
        for x in range(SIZE):
            raw.extend(pixel(x, y))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    print(f"wrote {OUT} ({len(png):,} bytes)")


if __name__ == "__main__":
    main()