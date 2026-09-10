"""A tiny software rasteriser, standard library only.

Enough to paint the texture templates -- rectangles, ellipses, polygons,
gradients, stipple and a 5x7 bitmap font for the guide overlays -- without
dragging in Pillow, so ``make textures`` works on a bare Python install and
inside Blender's bundled interpreter alike.

Coordinates are pixels with (0, 0) at the top-left.  Helpers that take a UV
rectangle flip V, because Blender's V axis points up and PNG rows go down.
"""

from __future__ import annotations

import math

from .png import write_png


def _b(c):
    return max(0, min(255, int(round(c * 255.0))))


class Canvas:
    def __init__(self, width, height, background=(0.0, 0.0, 0.0)):
        self.w = width
        self.h = height
        row = bytes((_b(background[0]), _b(background[1]), _b(background[2])))
        self.rows = [bytearray(row * width) for _ in range(height)]

    # -- basics ---------------------------------------------------------
    def fill(self, colour):
        row = bytes((_b(colour[0]), _b(colour[1]), _b(colour[2]))) * self.w
        for y in range(self.h):
            self.rows[y][:] = row

    def blend(self, x, y, colour, alpha=1.0):
        if alpha <= 0.0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        if alpha >= 1.0:
            i = x * 3
            self.rows[y][i] = _b(colour[0])
            self.rows[y][i + 1] = _b(colour[1])
            self.rows[y][i + 2] = _b(colour[2])
            return
        i = x * 3
        row = self.rows[y]
        inv = 1.0 - alpha
        row[i] = _b((row[i] / 255.0) * inv + colour[0] * alpha)
        row[i + 1] = _b((row[i + 1] / 255.0) * inv + colour[1] * alpha)
        row[i + 2] = _b((row[i + 2] / 255.0) * inv + colour[2] * alpha)

    def get(self, x, y):
        i = x * 3
        row = self.rows[max(0, min(self.h - 1, y))]
        return (row[i] / 255.0, row[i + 1] / 255.0, row[i + 2] / 255.0)

    # -- uv <-> pixels --------------------------------------------------
    def uv_to_px(self, u, v):
        return (u * self.w, (1.0 - v) * self.h)

    def rect_px(self, rect):
        """(u0, v0, u1, v1) -> integer pixel box (x0, y0, x1, y1)."""
        u0, v0, u1, v1 = rect
        x0, y1 = self.uv_to_px(u0, v0)
        x1, y0 = self.uv_to_px(u1, v1)
        return (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))

    # -- primitives -----------------------------------------------------
    def rect(self, x0, y0, x1, y1, colour, alpha=1.0):
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.w, x1), min(self.h, y1)
        if x1 <= x0 or y1 <= y0:
            return
        if alpha >= 1.0:
            seg = bytes((_b(colour[0]), _b(colour[1]),
                         _b(colour[2]))) * (x1 - x0)
            for y in range(y0, y1):
                self.rows[y][x0 * 3:x1 * 3] = seg
        else:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    self.blend(x, y, colour, alpha)

    def rect_outline(self, x0, y0, x1, y1, colour, width=2, alpha=1.0):
        self.rect(x0, y0, x1, y0 + width, colour, alpha)
        self.rect(x0, y1 - width, x1, y1, colour, alpha)
        self.rect(x0, y0, x0 + width, y1, colour, alpha)
        self.rect(x1 - width, y0, x1, y1, colour, alpha)

    def ellipse(self, cx, cy, rx, ry, colour, feather=1.2, alpha=1.0,
                inner=0.0):
        """Filled (or annular) ellipse with a soft edge."""
        rx, ry = max(0.5, rx), max(0.5, ry)
        x0 = max(0, int(cx - rx - feather - 1))
        x1 = min(self.w, int(cx + rx + feather + 2))
        y0 = max(0, int(cy - ry - feather - 1))
        y1 = min(self.h, int(cy + ry + feather + 2))
        for y in range(y0, y1):
            dy = (y + 0.5 - cy) / ry
            for x in range(x0, x1):
                dx = (x + 0.5 - cx) / rx
                d = math.hypot(dx, dy)
                # convert the normalised distance back to pixels for the
                # feather so thin and fat ellipses soften the same amount
                edge = (1.0 - d) * min(rx, ry)
                a = max(0.0, min(1.0, edge / feather + 0.5))
                if inner > 0.0:
                    inner_edge = (d - inner) * min(rx, ry)
                    a = min(a, max(0.0, min(1.0, inner_edge / feather + 0.5)))
                if a > 0.0:
                    self.blend(x, y, colour, a * alpha)

    def polygon(self, points, colour, alpha=1.0):
        """Scanline fill with 3x vertical supersampling for smooth edges."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h, int(max(ys)) + 1)
        n = len(points)
        cover = {}
        for y in range(y0, y1):
            for sub in (0.17, 0.5, 0.83):
                yy = y + sub
                xs = []
                for i in range(n):
                    ax, ay = points[i]
                    bx, by = points[(i + 1) % n]
                    if (ay <= yy < by) or (by <= yy < ay):
                        t = (yy - ay) / (by - ay)
                        xs.append(ax + t * (bx - ax))
                xs.sort()
                for k in range(0, len(xs) - 1, 2):
                    sx, ex = xs[k], xs[k + 1]
                    for x in range(max(0, int(sx)), min(self.w, int(ex) + 1)):
                        c = min(ex, x + 1.0) - max(sx, float(x))
                        if c > 0:
                            cover[(x, y)] = cover.get((x, y), 0.0) + c / 3.0
        for (x, y), c in cover.items():
            self.blend(x, y, colour, min(1.0, c) * alpha)

    def line(self, x0, y0, x1, y1, width, colour, alpha=1.0):
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * width * 0.5, dx / length * width * 0.5
        self.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                      (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], colour, alpha)

    def bar(self, cx, cy, length, width, angle_deg, colour, alpha=1.0):
        """A rotated rectangle -- the shirt's white flashes are made of these."""
        a = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        hl, hw = length * 0.5, width * 0.5
        pts = []
        for (sx, sy) in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)):
            pts.append((cx + sx * ca - sy * sa, cy + sx * sa + sy * ca))
        self.polygon(pts, colour, alpha)

    # -- gradients and texture -----------------------------------------
    def linear_gradient(self, box, c0, c1, vertical=True, alpha=1.0):
        x0, y0, x1, y1 = box
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(self.w, int(x1)), min(self.h, int(y1))
        span = (y1 - y0) if vertical else (x1 - x0)
        if span <= 0:
            return
        if vertical:
            for y in range(y0, y1):
                t = (y - y0) / span
                c = tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
                self.rect(x0, y, x1, y + 1, c, alpha)
        else:
            for x in range(x0, x1):
                t = (x - x0) / span
                c = tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
                self.rect(x, y0, x + 1, y1, c, alpha)

    def radial_shade(self, box, centre, radius, colour, power=1.6,
                     max_alpha=1.0):
        """Darken/tint outward from a point -- cheap ambient occlusion."""
        x0, y0, x1, y1 = (int(v) for v in box)
        cx, cy = centre
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                d = math.hypot(x - cx, y - cy) / radius
                if d >= 1.0:
                    continue
                self.blend(x, y, colour, ((1.0 - d) ** power) * max_alpha)

    def stipple(self, box, rng, count, colour, r_min=1.0, r_max=2.4,
                alpha=0.6, mask=None):
        x0, y0, x1, y1 = (int(v) for v in box)
        for _ in range(count):
            x = rng.uniform(x0, x1)
            y = rng.uniform(y0, y1)
            if mask is not None and not mask(x, y):
                continue
            self.ellipse(x, y, rng.uniform(r_min, r_max),
                         rng.uniform(r_min, r_max), colour,
                         feather=0.9, alpha=alpha * rng.uniform(0.55, 1.0))

    # -- text -----------------------------------------------------------
    def text(self, x, y, message, colour, scale=2, spacing=1):
        cx = x
        for ch in message.upper():
            glyph = FONT.get(ch)
            if glyph is None:
                cx += (5 + spacing) * scale
                continue
            for gy, line in enumerate(glyph):
                for gx, bit in enumerate(line):
                    if bit == "#":
                        self.rect(cx + gx * scale, y + gy * scale,
                                  cx + (gx + 1) * scale,
                                  y + (gy + 1) * scale, colour)
            cx += (5 + spacing) * scale
        return cx

    def text_width(self, message, scale=2, spacing=1):
        return len(message) * (5 + spacing) * scale

    # -- output ---------------------------------------------------------
    def save(self, path):
        return write_png(path, self.w, self.h, self.rows, channels=3)


# ---------------------------------------------------------------------------
# 5x7 bitmap font
# ---------------------------------------------------------------------------

def _glyph(*rows):
    return rows


FONT = {
    "A": _glyph(".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": _glyph("####.", "#...#", "####.", "#...#", "#...#", "#...#", "####."),
    "C": _glyph(".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": _glyph("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": _glyph("#####", "#....", "####.", "#....", "#....", "#....", "#####"),
    "F": _glyph("#####", "#....", "####.", "#....", "#....", "#....", "#...."),
    "G": _glyph(".####", "#....", "#....", "#..##", "#...#", "#...#", ".###."),
    "H": _glyph("#...#", "#...#", "#####", "#...#", "#...#", "#...#", "#...#"),
    "I": _glyph("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": _glyph("####.", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": _glyph("#...#", "#..#.", "##...", "#.#..", "#..#.", "#...#", "#...#"),
    "L": _glyph("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": _glyph("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": _glyph("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": _glyph(".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": _glyph("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": _glyph(".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": _glyph("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": _glyph(".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": _glyph("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": _glyph("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": _glyph("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": _glyph("#...#", "#...#", "#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": _glyph("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": _glyph("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": _glyph("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": _glyph(".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": _glyph("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": _glyph(".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": _glyph("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": _glyph("#..#.", "#..#.", "#..#.", "#####", "...#.", "...#.", "...#."),
    "5": _glyph("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": _glyph(".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": _glyph("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": _glyph(".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": _glyph(".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    "-": _glyph(".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "_": _glyph(".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    ".": _glyph(".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "/": _glyph("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    "(": _glyph("..##.", ".#...", "#....", "#....", "#....", ".#...", "..##."),
    ")": _glyph(".##..", "...#.", "....#", "....#", "....#", "...#.", ".##.."),
    "+": _glyph(".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    ":": _glyph(".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    " ": _glyph(".....", ".....", ".....", ".....", ".....", ".....", "....."),
}
