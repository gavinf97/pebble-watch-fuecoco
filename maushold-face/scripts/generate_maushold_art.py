"""Build the Maushold scene bitmap for a 1-bit Pebble (flint, 144x168) watchface.

Source: reference/maushold.webp — a cross-stitch pattern chart (67 stitches wide x 40 tall)
of Maushold (Family of 4). Fan sprite designed by Smogon user Travis, chart by
jack_of_all_threads / r/jackofallthreads; Pokemon (c) Nintendo. Used here as a
pixel-accurate silhouette guide only (the chart's own furniture — title box, DMC colour
key, Aida-size box and the outer black frame band — is deliberately excluded).

Run from the maushold-face/ directory: python3 scripts/generate_maushold_art.py
Writes resources/images/maushold_scene.png (144x107, pure 1-bit).

This differs from the Fuecoco script in two ways:

STAGE A (sprite) is the same cell-sampling + 3-zone ordered dither as fuecoco-face's
generate_fuecoco_art.py, but this chart needs THREE separate furniture masks rather than
Fuecoco's single top-right blanket. The fourth (smallest) Maushold sits at roughly cols
58-67 / rows 23-31 — right where a blanket mask would land — so masking it out would
silently amputate a family member.

STAGE B (scene) is new. Fuecoco floats on white; Maushold gets a world. The scene is
composed back-to-front in Python and baked into ONE bitmap, so the watch just blits it:
sky and clouds, far hills, a horizon grass band, per-foot contact shadows, the sprite
itself (cut out so the background shows around its silhouette), then grass tufts and
flowers drawn IN FRONT of the feet, and finally the ground line and soil band.

Two rules keep it from turning to mush on a 1-bit panel:

  * Different dither patterns for background vs character. The character is Bayer 4x4;
    background greys use regular lattices (LATTICE12/LATTICE25/CHECK50). Reusing Bayer for
    both would moire against the sprite's own texture.
  * An ink budget. Background ink coverage is asserted at the end; if the scene gets busier
    than BACKGROUND_INK_BUDGET it is over-decorated and something has to go.
"""
import os
from collections import deque

import numpy as np
from PIL import Image

HERE = os.path.dirname(__file__)
REFERENCE = os.path.join(HERE, "..", "reference", "maushold.webp")
OUT_PATH = os.path.join(HERE, "..", "resources", "images", "maushold_scene.png")

# --- Stage A: chart grid geometry (measured from the reference's gridlines) ---
COL_PITCH, ROW_PITCH = 26.0, 25.0
COL0, ROW0 = 25.0, 24.0
NCOLS, NROWS = 72, 42          # sampled extent: covers the sprite plus all chart furniture

# Chart furniture, in stitch-cell coordinates. Verified by rendering the sampled mosaic and
# reading off the boundaries — see the module docstring for why one mask isn't enough.
FRAME_COL_START = 69           # outer black frame band down the right edge
TITLE_ROWS, TITLE_COL_START = slice(0, 5), 61     # "Maushold (Family of 4)" box
KEY_ROWS, KEY_COL_START = slice(5, 17), 64        # DMC colour key
AIDA_ROWS, AIDA_COL_START = slice(36, 42), 61     # "Aida Dimensions" box

BLACK_CUTOFF = 75              # luminance <= this -> solid black, no dither
WHITE_CUTOFF = 185             # luminance >= this -> solid white, no dither
SCALE = 2                      # 67x40 stitches -> 134x80 px

BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]) / 16.0

# --- Stage B: scene geometry (screen coords within the scene layer) ---
SCENE_W, SCENE_H = 144, 107    # sits at GRect(0, 61, 144, 107) in src/c/maushold.c
SPRITE_X, SPRITE_Y = 5, 12     # 134 wide leaves a 5px margin each side; feet land near y91
# Clouds as (centre_x, centre_y, baseline_y, puffs) where each puff is (dx, dy, ry, rx).
# Placed by hand into the sky pockets the family actually leaves open — the full-width band
# above y12, the gaps between the three big heads, and the left/right margins. Sizes are
# deliberately mixed so the sky doesn't read as a row of identical stamps.
CLOUDS = (
    (26, 6, 11, ((-13, 2, 3, 6), (-3, -2, 5, 8), (8, 1, 4, 7), (16, 3, 3, 5))),   # big, top left
    (108, 6, 10, ((-11, 2, 3, 5), (-2, -1, 4, 7), (7, 1, 3, 6))),                 # medium, top right
    (90, 18, 21, ((-4, 1, 2, 3), (0, -1, 3, 4), (4, 1, 2, 3))),                   # small, between heads
    (47, 18, 20, ((-3, 0, 2, 3), (2, -1, 2, 3))),                                 # wisp, between heads
    (5, 20, 23, ((-4, 0, 2, 4), (1, -1, 2, 3))),                                  # wisp, left margin
    (138, 22, 25, ((-3, 0, 2, 3), (2, -1, 2, 3))),                                # wisp, right margin
)

GROUND_Y = 93                  # the 1px ground line
GRASS_BASE_Y = 94              # tufts stand on this row and rise
BACKGROUND_INK_BUDGET = 0.22   # max fraction of the scene the non-character art may ink

# Regular lattices for background greys — deliberately NOT Bayer (see docstring).
def _lattice(period, offsets):
    m = np.zeros((period, period), dtype=bool)
    for oy, ox in offsets:
        m[oy, ox] = True
    return m

LATTICE12 = _lattice(4, [(0, 0), (2, 2)])                    # 12.5% — far hills
LATTICE25 = _lattice(2, [(0, 0)])                            # 25%   — soil
LATTICE06 = _lattice(8, [(0, 0), (4, 4), (2, 6), (6, 2)])    # 6.25% — hills, fading out
CHECK50 = _lattice(2, [(0, 0), (1, 1)])                      # 50%   — shadows, soil crust


def tile(pattern, h, w, phase_y=0, phase_x=0):
    """Tile a lattice to (h, w), offset so adjacent regions don't share a phase."""
    p = pattern.shape[0]
    ys = (np.arange(h) + phase_y) % p
    xs = (np.arange(w) + phase_x) % p
    return pattern[np.ix_(ys, xs)]


# ---------------------------------------------------------------------------
# Stage A — extract the sprite from the chart
# ---------------------------------------------------------------------------

def extract_sprite_mosaic(img):
    """Sample each stitch cell's interior back into a clean, borderless mosaic."""
    arr = np.array(img.convert("RGB"))
    cells = np.zeros((NROWS, NCOLS, 3), dtype=np.float64)
    for r in range(NROWS):
        y0, y1 = int(ROW0 + r * ROW_PITCH) + 6, int(ROW0 + (r + 1) * ROW_PITCH) - 6
        for c in range(NCOLS):
            x0, x1 = int(COL0 + c * COL_PITCH) + 6, int(COL0 + (c + 1) * COL_PITCH) - 6
            if x1 > arr.shape[1] or y1 > arr.shape[0]:
                cells[r, c] = [255, 255, 255]
                continue
            cells[r, c] = arr[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)

    white = [255, 255, 255]
    cells[:, FRAME_COL_START:] = white
    cells[TITLE_ROWS, TITLE_COL_START:] = white
    cells[KEY_ROWS, KEY_COL_START:] = white
    cells[AIDA_ROWS, AIDA_COL_START:] = white
    return Image.fromarray(cells.astype(np.uint8))


def content_mask(mosaic):
    arr = np.array(mosaic.convert("RGB"))
    return ~((arr[:, :, 0] > 250) & (arr[:, :, 1] > 250) & (arr[:, :, 2] > 250))


def crop_to_content(mosaic):
    nonwhite = content_mask(mosaic)
    rows, cols = np.where(nonwhite.any(axis=1))[0], np.where(nonwhite.any(axis=0))[0]
    return mosaic.crop((int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1))


def dither(gray, scale):
    """3-zone ordered dither: snap the extremes, texture only the midtones."""
    big = np.array(gray.resize((gray.width * scale, gray.height * scale), Image.NEAREST)).astype(np.float64)
    h, w = big.shape
    thresh = np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]
    norm = np.clip((big - BLACK_CUTOFF) / (WHITE_CUTOFF - BLACK_CUTOFF), 0.0, 1.0)
    out = np.where(big <= BLACK_CUTOFF, 0, np.where(big >= WHITE_CUTOFF, 255, np.where(norm > thresh, 255, 0)))
    return out.astype(np.uint8)


def build_sprite():
    """Returns (ink, opaque): ink[y,x] True where black, opaque[y,x] True inside the silhouette.

    The silhouette comes from the *stitch mosaic*, not from the dithered bitmap. A flood fill
    over the dithered pixels leaks: the mice's grey fur is a 50%-ish Bayer texture whose white
    pixels form a 4-connected path from the outside straight into their heads, so the fill
    swallows the character and the background texture shows through it. At stitch resolution
    there is no ambiguity — a cell is either charted or it is blank paper.
    """
    mosaic = extract_sprite_mosaic(Image.open(REFERENCE))
    cropped = crop_to_content(mosaic)
    opaque = np.kron(content_mask(cropped), np.ones((SCALE, SCALE), dtype=bool))
    ink = dither(cropped.convert("L"), SCALE) == 0
    return ink & opaque, opaque


# ---------------------------------------------------------------------------
# Stage B — compose the scene
# ---------------------------------------------------------------------------

def disc(cy, cx, ry, rx):
    """Boolean ellipse mask over the scene canvas."""
    yy, xx = np.ogrid[0:SCENE_H, 0:SCENE_W]
    return ((yy - cy) / float(ry)) ** 2 + ((xx - cx) / float(rx)) ** 2 <= 1.0


def outline_of(mask):
    """1px outline: the mask minus its 4-neighbour erosion."""
    e = mask.copy()
    e[1:, :] &= mask[:-1, :]
    e[:-1, :] &= mask[1:, :]
    e[:, 1:] &= mask[:, :-1]
    e[:, :-1] &= mask[:, 1:]
    return mask & ~e


def draw_cloud(ink, cx, cy, base_y, puffs):
    """An outlined puff with a flat bottom and a sparse interior, so it stays airy.

    Filling a cloud solid on a 1-bit panel gives you a black blob; outlining it and letting
    the lattice suggest volume is what keeps it reading as a cloud at this size.
    """
    body = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    for dx, dy, ry, rx in puffs:
        body |= disc(cy + dy, cx + dx, ry, rx)
    body[base_y + 1:, :] = False
    edge = outline_of(body)
    ink |= edge
    ink |= (body & ~edge) & tile(LATTICE12, SCENE_H, SCENE_W, phase_x=cx, phase_y=cy)


def draw_sky(ink):
    for cx, cy, base_y, puffs in CLOUDS:
        draw_cloud(ink, cx, cy, base_y, puffs)


def draw_shadows(ink, opaque):
    """A shadow that hugs the silhouette's bottom contour, column by column.

    Grouping feet into runs and dropping one ellipse under each is what you would do for a
    single character, but the four mice overlap: neighbouring runs merge into one 52px-wide
    blob, and a run whose lowest pixel is a belly rather than a foot drops a shadow in mid
    air. Shading directly beneath whatever ink is lowest in each column cannot float, and it
    traces all four bodies for free.
    """
    h, w = opaque.shape
    core = np.zeros((SCENE_H, SCENE_W), dtype=bool)    # contact row, darkest
    penumbra = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    for x in range(w):
        ys = np.where(opaque[:, x])[0]
        if not len(ys):
            continue
        b = ys.max()
        if b < h - 12:
            continue  # this column bottoms out too high to be touching the ground
        sx = SPRITE_X + x
        for d in (1, 2, 3):
            sy = SPRITE_Y + b + d
            if 0 <= sy < SCENE_H and 0 <= sx < SCENE_W:
                (core if d == 1 else penumbra)[sy, sx] = True
    # One pixel of horizontal spread, so the shadow isn't a hard tracing of the outline.
    for m in (core, penumbra):
        edge = m.copy()
        m[:, 1:] |= edge[:, :-1]
        m[:, :-1] |= edge[:, 1:]
    # Graded: a flat 50% under every body turns to mud where it meets the mice's own
    # dithered legs. Dark only on the contact row, light beneath it.
    ink |= core & tile(CHECK50, SCENE_H, SCENE_W)
    ink |= penumbra & ~core & tile(LATTICE25, SCENE_H, SCENE_W)


def draw_blade(ink, x, y_base, height, lean):
    """One grass blade, leaning as it rises, thickened at the base."""
    for i in range(height):
        y = y_base - i
        if not (0 <= y < SCENE_H):
            break
        xo = int(round(x + lean * (i / float(max(1, height - 1))) ** 2))
        if 0 <= xo < SCENE_W:
            ink[y, xo] = True
            if i < 2 and 0 <= xo + 1 < SCENE_W:
                ink[y, xo + 1] = True


def draw_flower(ink, x, y_base, height):
    for i in range(height):
        y = y_base - i
        if 0 <= y < SCENE_H:
            ink[y, x] = True
    top = y_base - height
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        y, xx = top + dy, x + dx
        if 0 <= y < SCENE_H and 0 <= xx < SCENE_W:
            ink[y, xx] = True


def draw_ground(ink, rng):
    """Ground line, soil band and pebbles. The line wobbles so it doesn't read as a ruler."""
    wobble = 0
    for x in range(SCENE_W):
        if rng.random() < 0.12:
            wobble = int(np.clip(wobble + rng.choice([-1, 1]), -1, 1))
        y = GROUND_Y + wobble
        ink[y, x] = True

    soil = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    soil[GROUND_Y + 1:, :] = True
    crust = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    crust[GROUND_Y + 1:GROUND_Y + 3, :] = True
    ink |= crust & tile(CHECK50, SCENE_H, SCENE_W)
    ink |= soil & ~crust & tile(LATTICE25, SCENE_H, SCENE_W, phase_y=1, phase_x=1)

    for _ in range(6):
        px = rng.integers(4, SCENE_W - 6)
        py = rng.integers(GROUND_Y + 4, SCENE_H - 3)
        ink[py:py + 2, px:px + 3] = True


def draw_grass(ink, rng):
    """Tufts in FRONT of the sprite, denser at the edges to frame, sparse in the middle so
    the mice's legs stay readable."""
    x = 1
    while x < SCENE_W - 2:
        edge = min(x, SCENE_W - 1 - x) < 26
        gap = rng.integers(3, 6) if edge else rng.integers(7, 15)
        blades = rng.integers(2, 4) if edge else rng.integers(1, 3)
        for b in range(int(blades)):
            bx = x + b * 2
            if bx >= SCENE_W - 2:
                break
            h = int(rng.integers(5, 11) if edge else rng.integers(4, 8))
            draw_blade(ink, bx, GRASS_BASE_Y, h, rng.choice([-2, -1, 1, 2]))
        if rng.random() < 0.16:
            draw_flower(ink, min(SCENE_W - 2, x + 1), GRASS_BASE_Y - 1, int(rng.integers(4, 7)))
        x += int(gap)


def compose():
    ink_sprite, opaque = build_sprite()
    sh, sw = ink_sprite.shape

    background = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    rng = np.random.default_rng(20260905)

    draw_sky(background)
    draw_shadows(background, opaque)

    # Clouds must never touch the family. Cheaper to assert than to spot by eye at 144px.
    covered = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    covered[SPRITE_Y:SPRITE_Y + sh, SPRITE_X:SPRITE_X + sw] = opaque
    halo = covered.copy()
    halo[1:, :] |= covered[:-1, :]
    halo[:-1, :] |= covered[1:, :]
    halo[:, 1:] |= covered[:, :-1]
    halo[:, :-1] |= covered[:, 1:]
    sky_only = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    draw_sky(sky_only)
    clash = np.argwhere(sky_only & halo)
    if len(clash):
        raise SystemExit("cloud collides with the family at %s — move it or shrink it"
                         % clash[:5].tolist())

    scene = background.copy()

    # Paste the sprite through its cutout mask, so hills and grass show around the silhouette.
    ys, xs = slice(SPRITE_Y, SPRITE_Y + sh), slice(SPRITE_X, SPRITE_X + sw)
    region = scene[ys, xs]
    region[opaque] = ink_sprite[opaque]
    scene[ys, xs] = region

    foreground = np.zeros((SCENE_H, SCENE_W), dtype=bool)
    draw_grass(foreground, rng)
    draw_ground(foreground, rng)
    scene |= foreground

    decor = background | foreground
    coverage = decor.sum() / float(decor.size)
    if coverage > BACKGROUND_INK_BUDGET:
        raise SystemExit(
            "background ink coverage %.1f%% exceeds the %.0f%% budget — the scene is "
            "over-decorated. Drop the clouds first, then the flowers."
            % (coverage * 100, BACKGROUND_INK_BUDGET * 100))

    return scene, coverage, sw, sh


if __name__ == "__main__":
    scene, coverage, sw, sh = compose()
    out = np.where(scene, 0, 255).astype(np.uint8)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    Image.fromarray(out).convert("1").save(OUT_PATH)
    print("wrote %s (%dx%d)" % (OUT_PATH, SCENE_W, SCENE_H))
    print("  sprite %dx%d at (%d,%d); background ink %.1f%% of budget %.0f%%"
          % (sw, sh, SPRITE_X, SPRITE_Y, coverage * 100, BACKGROUND_INK_BUDGET * 100))
