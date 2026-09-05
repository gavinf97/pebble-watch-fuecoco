"""Generate the 1-bit weather icon set for the Maushold watchface (flint, 144x168).

Run from the maushold-face/ directory: python3 scripts/generate_weather_icons.py
Writes resources/images/wx/*.png (26x26 each) plus a scaled contact sheet for review.

Why sprites instead of drawing at runtime: the Fuecoco face draws its weather with
graphics_fill_rect/graphics_draw_line in an update_proc, which on a 1-bit panel gives you a
rounded blob and three diagonal scratches for every wet condition — rain, drizzle, sleet and
showers are literally indistinguishable, and the "cloud" reads as a pill. Pixel art authored
at the exact display size can carry a real icon vocabulary, and 26x26 1-bit PNGs cost ~100
bytes each against a 1MB resource budget.

The visual language, which is what makes the set readable as a *set*:
  * Sun and moon are SOLID black — they are the only solid shapes, so "is it clear?" is
    answerable at a glance without reading detail.
  * Clouds are 1px OUTLINES with white interiors, so whatever sits under them (drops,
    flakes, a bolt) stays legible instead of fighting a black mass.
  * Cloud *quantity* encodes sky cover: sun alone -> sun + wisps -> sun behind one cloud ->
    two clouds and no sun. That is the axis that actually varies day to day in Ireland/UK.
  * Precipitation type is carried by the accent glyph below the cloud, and intensity by how
    many of them there are.
"""
import os

import numpy as np
from PIL import Image

SIZE = 26
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "wx")
SHEET = os.path.join(os.path.dirname(__file__), "..", "reference", "weather_contact_sheet.png")

# Small glyphs are hand-mapped rather than derived — at this size a snowflake or a bolt is a
# specific arrangement of a dozen pixels, and no primitive gets you there.
GLYPHS = {
    "flake": [
        "..#..",
        "#.#.#",
        ".###.",
        "#.#.#",
        "..#..",
    ],
    "flake_small": [
        ".#.",
        "###",
        ".#.",
    ],
    "bolt": [
        "...####",
        "..####.",
        ".####..",
        "#######",
        "..####.",
        ".####..",
        "####...",
        ".##....",
        ".#.....",
    ],
    "query": [
        ".###.",
        "#...#",
        "....#",
        "...#.",
        "..#..",
        ".....",
        "..#..",
    ],
    "drop": [
        ".#.",
        ".#.",
        "###",
        ".#.",
    ],
}


def canvas():
    return np.zeros((SIZE, SIZE), dtype=bool)


def disc(cy, cx, r):
    yy, xx = np.ogrid[0:SIZE, 0:SIZE]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def outline_of(mask):
    e = mask.copy()
    e[1:, :] &= mask[:-1, :]
    e[:-1, :] &= mask[1:, :]
    e[:, 1:] &= mask[:, :-1]
    e[:, :-1] &= mask[:, 1:]
    return mask & ~e


def put(cv, glyph, top, left):
    for dy, row in enumerate(GLYPHS[glyph]):
        for dx, ch in enumerate(row):
            if ch == "#":
                y, x = top + dy, left + dx
                if 0 <= y < SIZE and 0 <= x < SIZE:
                    cv[y, x] = True


def line(cv, y0, x0, y1, x1):
    n = max(abs(y1 - y0), abs(x1 - x0))
    for i in range(n + 1):
        t = i / float(n) if n else 0.0
        y, x = int(round(y0 + (y1 - y0) * t)), int(round(x0 + (x1 - x0) * t))
        if 0 <= y < SIZE and 0 <= x < SIZE:
            cv[y, x] = True


def sun(cv, cy, cx, r, ray_gap, ray_len):
    cv |= disc(cy, cx, r)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        norm = (dy * dy + dx * dx) ** 0.5
        uy, ux = dy / norm, dx / norm
        line(cv, round(cy + uy * ray_gap), round(cx + ux * ray_gap),
             round(cy + uy * (ray_gap + ray_len)), round(cx + ux * (ray_gap + ray_len)))


def moon(cv, cy, cx, r):
    """Crescent: a disc with a second, offset disc bitten out of it."""
    cv |= disc(cy, cx, r) & ~disc(cy - 2, cx + 4, r - 0.5)


def cloud_body(cy, cx, scale=1.0):
    body = (disc(cy + 2 * scale, cx - 6 * scale, 4 * scale)
            | disc(cy - 2 * scale, cx - 1 * scale, 6 * scale)
            | disc(cy + 1 * scale, cx + 6 * scale, 5 * scale))
    flat = int(round(cy + 6 * scale))
    body[flat + 1:, :] = False
    return body


def add_cloud(cv, cy, cx, scale=1.0):
    """Draw a cloud that properly occludes whatever is already on the canvas."""
    body = cloud_body(cy, cx, scale)
    cv &= ~body          # punch out the sun/moon behind it
    cv |= outline_of(body)
    return body


def wisps(cv, rows):
    for y, x0, x1 in rows:
        line(cv, y, x0, y, x1)


# --- the icons -------------------------------------------------------------

def i_sun():
    cv = canvas(); sun(cv, 13, 13, 5.6, 8, 3); return cv


def i_moon():
    cv = canvas(); moon(cv, 13, 12, 8)
    put(cv, "flake_small", 3, 19); put(cv, "flake_small", 17, 20)
    return cv


def i_sun_haze():
    cv = canvas(); sun(cv, 10, 10, 5.0, 7, 3); add_cloud(cv, 20, 17, 0.58); return cv


def i_moon_haze():
    cv = canvas(); moon(cv, 10, 10, 6.5); add_cloud(cv, 20, 17, 0.58); return cv


def i_sun_cloud():
    cv = canvas(); sun(cv, 8, 8, 4.2, 6, 3); add_cloud(cv, 16, 14, 0.95); return cv


def i_moon_cloud():
    cv = canvas(); moon(cv, 8, 8, 6); add_cloud(cv, 16, 14, 0.95); return cv


def i_cloud():
    """Overcast: one big cloud with a hatched interior.

    Two overlapping outlined clouds was the first attempt and it just reads as one lumpy
    mass at 26px — the shared outline fuses them. Texture is the clearer signal: every other
    cloud in the set is hollow, so the one filled cloud unmistakably means 'socked in'.
    """
    cv = canvas()
    body = cloud_body(14, 12, 1.15)
    edge = outline_of(body)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    cv |= edge
    cv |= (body & ~edge) & (((yy % 2) == 0) & ((xx % 2) == 0))
    return cv


def _precip_cloud(cv):
    return add_cloud(cv, 9, 13, 0.95)


def i_fog():
    cv = canvas(); _precip_cloud(cv)
    wisps(cv, [(18, 3, 21), (21, 6, 24), (24, 3, 18)])
    return cv


def i_drizzle():
    cv = canvas(); _precip_cloud(cv)
    for x in (6, 12, 18):
        line(cv, 18, x, 19, x - 1)
    for x in (9, 15):
        line(cv, 22, x, 23, x - 1)
    return cv


def i_frz_drizzle():
    cv = canvas(); _precip_cloud(cv)
    for x in (6, 12):
        line(cv, 18, x, 19, x - 1)
    put(cv, "flake_small", 20, 15)
    return cv


def i_rain():
    cv = canvas(); _precip_cloud(cv)
    for x in (6, 12, 18):
        line(cv, 18, x + 2, 22, x - 1)
    return cv


def i_rain_heavy():
    cv = canvas(); _precip_cloud(cv)
    for x in (4, 9, 14, 19, 24):
        line(cv, 18, x + 2, 24, x - 2)
    return cv


def i_sleet():
    cv = canvas(); _precip_cloud(cv)
    line(cv, 18, 8, 22, 5)
    line(cv, 18, 21, 22, 18)
    put(cv, "flake_small", 19, 11)
    return cv


def i_snow():
    cv = canvas(); _precip_cloud(cv)
    put(cv, "flake", 18, 3); put(cv, "flake", 20, 10); put(cv, "flake", 18, 17)
    return cv


def i_snow_heavy():
    cv = canvas(); _precip_cloud(cv)
    put(cv, "flake", 17, 2); put(cv, "flake", 17, 10); put(cv, "flake", 17, 18)
    put(cv, "flake_small", 23, 6); put(cv, "flake_small", 23, 15)
    return cv


def i_storm():
    cv = canvas(); _precip_cloud(cv); put(cv, "bolt", 17, 10); return cv


def i_storm_hail():
    cv = canvas(); _precip_cloud(cv); put(cv, "bolt", 17, 12)
    cv |= disc(20, 4, 1.6); cv |= disc(24, 8, 1.6)
    return cv


def i_wind():
    cv = canvas()
    add_cloud(cv, 8, 12, 0.85)
    for y, x1 in ((17, 18), (21, 21), (25, 15)):
        line(cv, y, 2, y, x1)
        line(cv, y, x1, y - 1, x1 - 2)      # the hook that says 'moving air', not 'fog'
        line(cv, y - 1, x1 - 2, y - 2, x1 - 3)
    return cv


def i_nodata():
    cv = canvas()
    ring = disc(13, 13, 10) & ~disc(13, 13, 9)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    cv |= ring & (((yy + xx) % 4) < 2)      # dotted, so it reads as 'pending' not 'a state'
    put(cv, "query", 9, 11)
    return cv


ICONS = [
    ("WX_SUN", i_sun), ("WX_MOON", i_moon),
    ("WX_SUN_HAZE", i_sun_haze), ("WX_MOON_HAZE", i_moon_haze),
    ("WX_SUN_CLOUD", i_sun_cloud), ("WX_MOON_CLOUD", i_moon_cloud),
    ("WX_CLOUD", i_cloud), ("WX_FOG", i_fog),
    ("WX_DRIZZLE", i_drizzle), ("WX_FRZ_DRIZZLE", i_frz_drizzle),
    ("WX_RAIN", i_rain), ("WX_RAIN_HEAVY", i_rain_heavy),
    ("WX_SLEET", i_sleet), ("WX_SNOW", i_snow), ("WX_SNOW_HEAVY", i_snow_heavy),
    ("WX_STORM", i_storm), ("WX_STORM_HAIL", i_storm_hail),
    ("WX_WIND", i_wind), ("WX_NODATA", i_nodata),
]


def contact_sheet(rendered, scale=4, cols=5):
    rows = (len(rendered) + cols - 1) // cols
    pad, cell = 3, SIZE + 3
    sheet = np.ones((rows * cell * scale, cols * cell * scale), dtype=np.uint8) * 255
    for i, (_, cv) in enumerate(rendered):
        r, c = divmod(i, cols)
        block = np.kron(np.where(cv, 0, 255).astype(np.uint8), np.ones((scale, scale), np.uint8))
        y, x = (r * cell + pad) * scale, (c * cell + pad) * scale
        sheet[y:y + SIZE * scale, x:x + SIZE * scale] = block
    return Image.fromarray(sheet)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    rendered = []
    for name, fn in ICONS:
        cv = fn()
        rendered.append((name, cv))
        img = Image.fromarray(np.where(cv, 0, 255).astype(np.uint8)).convert("1")
        img.save(os.path.join(OUT_DIR, name.lower() + ".png"))
    contact_sheet(rendered).save(SHEET)
    print("wrote %d icons (%dx%d) to %s" % (len(rendered), SIZE, SIZE, OUT_DIR))
    print("contact sheet: %s" % SHEET)
