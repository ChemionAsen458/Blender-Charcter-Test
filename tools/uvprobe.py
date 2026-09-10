"""Look up where a 3D point on the model lands in texture space.

The texture templates need to put a blush on the cheek, a white flash on
the chest or a stripe on a shoe *at a specific place on the model*.  Rather
than hand-deriving each UV, the generator builds the mesh, hands it to a
probe, and asks: "what UV is this point?"  Details then stay put when the
proportions or the atlas layout change.
"""

from __future__ import annotations

import math


class UVProbe:
    def __init__(self, meshdata, rect=None, margin=0.002):
        """Index every vertex/UV pair, optionally only inside `rect`."""
        self.samples = []
        for face, uvs in zip(meshdata.faces, meshdata.uvs):
            for vi, uv in zip(face, uvs):
                if rect is not None:
                    u0, v0, u1, v1 = rect
                    if not (u0 - margin <= uv[0] <= u1 + margin
                            and v0 - margin <= uv[1] <= v1 + margin):
                        continue
                self.samples.append((meshdata.verts[vi], uv))
        if not self.samples:
            raise ValueError("UVProbe: no samples in the requested rect")

    def uv_at(self, point, k=6, seam_tolerance=0.06):
        """Inverse-distance blend of the nearest samples' UVs.

        Samples whose UV is far from the closest one are dropped, so
        probing next to a seam does not average the two sides together
        into a UV somewhere in the middle of the texture.
        """
        px, py, pz = point
        scored = []
        for (q, uv) in self.samples:
            d2 = (q[0] - px) ** 2 + (q[1] - py) ** 2 + (q[2] - pz) ** 2
            scored.append((d2, uv))
        scored.sort(key=lambda s: s[0])
        best_uv = scored[0][1]
        acc_u = acc_v = total = 0.0
        for (d2, uv) in scored[:k]:
            if math.hypot(uv[0] - best_uv[0], uv[1] - best_uv[1]) > seam_tolerance:
                continue
            w = 1.0 / (d2 + 1e-8)
            acc_u += uv[0] * w
            acc_v += uv[1] * w
            total += w
        if total == 0.0:
            return best_uv
        return (acc_u / total, acc_v / total)

    def uv_scale(self, point, delta=0.02):
        """Roughly how many UV units one metre spans near `point`.

        Returned as (du_per_m, dv_per_m) using the two directions that move
        fastest in U and V, which is accurate enough to size a blush or a
        stripe consistently across differently stretched islands.
        """
        base = self.uv_at(point)
        best_u = best_v = 0.0
        for axis in ((delta, 0, 0), (0, delta, 0), (0, 0, delta)):
            q = (point[0] + axis[0], point[1] + axis[1], point[2] + axis[2])
            uv = self.uv_at(q)
            best_u = max(best_u, abs(uv[0] - base[0]) / delta)
            best_v = max(best_v, abs(uv[1] - base[1]) / delta)
        return (max(best_u, 1e-3), max(best_v, 1e-3))
