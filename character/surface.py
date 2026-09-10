"""Sampling the skin surface so add-on parts sit flush against it.

Eyes, eyelids, brows, the mouth and the hair cap all have to hug the head.
Rather than duplicating the head's shaping maths, they ask this module
where the skin actually ended up: it does an inverse-distance blend over
the front-facing body vertices near a point, which is smooth, cheap and
automatically stays correct when the proportions in ``config`` change.
"""

from __future__ import annotations

import math


class FrontSampler:
    """Front-surface lookup: given (x, z) on the face, return y."""

    def __init__(self, meshdata, z_range=(1.40, 1.75), max_y=0.02):
        self.points = [(vx, vz, vy) for (vx, vy, vz) in meshdata.verts
                       if z_range[0] <= vz <= z_range[1] and vy < max_y]
        if not self.points:
            raise ValueError("no front-facing verts in the sample range")

    def y_at(self, x, z, radius=0.030, front_band=0.020):
        """Inverse-distance blend of the frontmost skin near (x, z)."""
        near = []
        r2 = radius * radius
        for (px, pz, py) in self.points:
            d2 = (px - x) ** 2 + (pz - z) ** 2
            if d2 <= r2:
                near.append((d2, py))
        if not near:
            # widen once rather than failing at the edge of the face
            return self.y_at(x, z, radius * 2.0, front_band)
        front = min(p[1] for p in near)
        near = [p for p in near if p[1] <= front + front_band]
        total = 0.0
        acc = 0.0
        for (d2, py) in near:
            w = 1.0 / (d2 + 1e-7)
            acc += py * w
            total += w
        return acc / total

    def normal_at(self, x, z, eps=0.006):
        """Approximate outward (front) normal of the skin at (x, z)."""
        dydx = (self.y_at(x + eps, z) - self.y_at(x - eps, z)) / (2 * eps)
        dydz = (self.y_at(x, z + eps) - self.y_at(x, z - eps)) / (2 * eps)
        # surface F(x,z) = y  ->  normal proportional to (dydx, -1, dydz)
        nx, ny, nz = dydx, -1.0, dydz
        n = math.sqrt(nx * nx + ny * ny + nz * nz)
        return (nx / n, ny / n, nz / n)

    def offset_point(self, x, z, offset):
        """A point `offset` metres out from the skin along its normal."""
        y = self.y_at(x, z)
        nx, ny, nz = self.normal_at(x, z)
        return (x + nx * offset, y + ny * offset, z + nz * offset)


def lens(u, half_top, half_bottom, top_power=0.62, bottom_power=0.78,
         peak_shift=0.0):
    """Top and bottom edges of an almond/lens outline at across-parameter u.

    `u` runs -1 (one corner) to +1 (the other).  `peak_shift` slides the
    tallest point of the upper arc sideways, which is what gives an anime
    eye its slightly asymmetric, alert shape.
    """
    uu = max(-1.0, min(1.0, u))
    base = max(0.0, 1.0 - uu * uu)
    shift = 1.0 + peak_shift * uu
    top = half_top * (base ** top_power) * max(0.0, shift)
    bottom = -half_bottom * (base ** bottom_power)
    return bottom, top
