"""Extract a black/white Fuecoco sprite from the reference cross-stitch chart for a 1-bit
Pebble (flint, 144x168) watchface — using ordered dithering to keep the shading nuance from
the original multi-colour art instead of collapsing everything to flat black/white.

Source: reference/fuecpix.png — a cross-stitch pattern chart (41 stitches wide x 49 tall)
with a DMC color-swatch legend box in the top-right. Fan sprite designed by Smogon user
KingOfThe-X-Roads; Pokemon (c) Nintendo. Used here as a pixel-accurate silhouette guide only
(the legend/colour-key panel and grid border are deliberately excluded from the output).

Run from the fuecoco-face/ directory: python3 scripts/generate_fuecoco_art.py
Writes resources/images/fuecoco.png (82x98, pure 1-bit, no grid lines).

How it works:
1. The chart draws each stitch as a ~26x25px cell on a grid; we sample the average colour
   of each cell's interior (avoiding the black gridlines) to rebuild a clean, borderless
   mosaic at native 41x49 resolution.
2. The legend box (title + Aida-size + DMC colour key) occupies known rows/columns to the
   top-right of the sprite and is whited out explicitly — it is a separate graphic, not
   part of the character, and must not leak into the silhouette.
3. The Pebble 2 Duo's display is strictly 1-bit — there is no real gray. So "gray" has to be
   *simulated* with dithering (an alternating black/white pixel pattern that reads as a mid
   tone at a glance), the same technique e-paper/e-ink devices have always used for this.
   A flat luminance threshold collapses the whole sprite to two tones and loses most of its
   features (the red back marking, the flame crest, the belly patch all become one black
   blob). Instead we use a 3-zone ordered (Bayer 4x4) dither:
     - truly dark pixels (outline, pupils)      -> solid black, no dither
     - truly light pixels (cream face/highlight) -> solid white, no dither
     - everything in between (the back marking, crest, belly patch, tail shading)
       -> dithered, with density following the source luminance, so those regions read as
       distinct textured grays instead of collapsing into the outline or the background.
4. The result is scaled 2x with nearest-neighbour (no smoothing) for a crisp pixel-art look.

Tweak BLACK_CUTOFF/WHITE_CUTOFF below to widen/narrow the dithered midtone band, or SCALE to
change the output size (must still fit the GRect used in src/c/fuecoco.c).
"""
import os
import numpy as np
from PIL import Image

REFERENCE = os.path.join(os.path.dirname(__file__), "..", "reference", "fuecpix.png")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "fuecoco.png")

# Chart grid geometry (measured from the reference PNG's gridlines).
COL_PITCH, ROW_PITCH = 26.0, 25.0
COL0, ROW0 = 26.0, 25.0
NCOLS, NROWS = 42, 50          # sampled grid extent (covers sprite + legend area)
LEGEND_ROW_CUTOFF = 30         # legend content only ever appears in rows < this...
LEGEND_COL_START = 31          # ...and columns >= this

BLACK_CUTOFF = 75              # luminance <= this -> solid black, no dither
WHITE_CUTOFF = 185             # luminance >= this -> solid white, no dither
SCALE = 2                      # integer upscale for a visible but still crisp sprite

# Classic 4x4 ordered (Bayer) dither matrix, normalized to 0..1 thresholds.
BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]) / 16.0


def extract_sprite_mosaic(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    cells = np.zeros((NROWS, NCOLS, 3), dtype=np.float64)
    for r in range(NROWS):
        y0, y1 = int(ROW0 + r * ROW_PITCH) + 6, int(ROW0 + (r + 1) * ROW_PITCH) - 6
        for c in range(NCOLS):
            x0, x1 = int(COL0 + c * COL_PITCH) + 6, int(COL0 + (c + 1) * COL_PITCH) - 6
            cells[r, c] = arr[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)

    cells[0:LEGEND_ROW_CUTOFF, LEGEND_COL_START:NCOLS] = [255, 255, 255]
    return Image.fromarray(cells.astype(np.uint8))


def crop_to_content(mosaic: Image.Image) -> Image.Image:
    arr = np.array(mosaic.convert("RGB"))
    nonwhite = ~((arr[:, :, 0] > 250) & (arr[:, :, 1] > 250) & (arr[:, :, 2] > 250))
    rows, cols = np.where(nonwhite.any(axis=1))[0], np.where(nonwhite.any(axis=0))[0]
    return mosaic.crop((int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1))


def dither(gray: Image.Image, scale: int) -> Image.Image:
    big = np.array(gray.resize((gray.width * scale, gray.height * scale), Image.NEAREST)).astype(np.float64)
    h, w = big.shape
    thresh = np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]

    # Normalize luminance within the midtone band only; outside it, snap to clean black/white.
    norm = np.clip((big - BLACK_CUTOFF) / (WHITE_CUTOFF - BLACK_CUTOFF), 0.0, 1.0)
    out = np.where(big <= BLACK_CUTOFF, 0, np.where(big >= WHITE_CUTOFF, 255, np.where(norm > thresh, 255, 0)))
    return Image.fromarray(out.astype(np.uint8)).convert("1")


if __name__ == "__main__":
    reference = Image.open(REFERENCE)
    mosaic = extract_sprite_mosaic(reference)
    cropped = crop_to_content(mosaic).convert("L")
    mono = dither(cropped, SCALE)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    mono.save(OUT_PATH)
    print(f"wrote {OUT_PATH} ({mono.width}x{mono.height}, native sprite was {cropped.width}x{cropped.height})")
