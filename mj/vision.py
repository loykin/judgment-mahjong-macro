"""Reading the mahjong table from a 1920x1080 frame (numpy array, H x W x 3, RGB).

The closed hand sits at the bottom, left-aligned: tile i's face starts at x = 396 + 73.5 * i and is about
66 x 90 pixels. The tile under the cursor is raised by about 16 pixels. Melds (pon/chi) are drawn further
right and are not part of the hand row. Tiles are told apart by comparing with the pictures in
templates/hand (name_N.png), which were cut from real frames.
"""
import glob
import os

import numpy as np

from . import engine

X0, PITCH, W, H = 396, 73.5, 66, 90
SLOTS = 15
# a tile matches a template when the mean difference is below MATCH, or below LOOSE when the next
# different tile is clearly further (the raised cursor tile looks a little different)
MATCH = 22.0
LOOSE, MARGIN = 35.0, 6.0
# the call/win prompt box (bottom right) and the "○ cancel" line under it
PROMPT = (1540, 920, 1900, 1050)


def _load_png(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert('RGB'))


class Templates:
    def __init__(self, folder):
        self.names, pics = [], []
        for f in sorted(glob.glob(os.path.join(folder, '*.png'))):
            self.names.append(os.path.basename(f).split('_')[0])
            pics.append(_load_png(f).astype(np.int16))
        if not pics:
            raise RuntimeError(f'no tile pictures in {folder}')
        self.pics = np.stack(pics)  # N x H x W x 3

    def match(self, tile):
        """(name, distance, margin to the next different name)."""
        d = np.abs(self.pics - tile.astype(np.int16)[None]).mean(axis=(1, 2, 3))
        order = np.argsort(d)
        best = self.names[order[0]]
        other = next((d[k] for k in order[1:] if self.names[k] != best), 255.0)
        return best, float(d[order[0]]), float(other - d[order[0]])


class Slot:
    __slots__ = ('index', 'name', 'dist', 'raised', 'crop')  # raised: top y while reading, then bool

    def __init__(self, index, name, dist, raised, crop):
        self.index, self.name, self.dist, self.raised, self.crop = index, name, dist, raised, crop

    def __repr__(self):
        return f'{self.name or "?"}{"^" if self.raised else ""}'


def hand_slots(img, templates):
    """The tiles in the hand row, left to right. A slot with name None looked like a tile face but matched
    no template (a tile not seen before, or an animation)."""
    out = []
    for i in range(SLOTS):
        x = int(X0 + PITCH * i)
        if x + W > img.shape[1]:
            break
        # the hand's top edge is at y ~910 (~894 when raised); start below the discard rows above it
        col = img[882:960, x + 12:x + W - 12].min(axis=2).mean(axis=1)
        top = next((y for y in range(len(col)) if col[y] > 185), None)
        if top is None:
            continue
        y = 882 + top
        crop = img[y + 2:y + 2 + H, x:x + W]
        if crop.shape[:2] != (H, W) or (crop.min(axis=2) > 170).mean() < 0.45:
            continue
        name, dist, margin = templates.match(crop)
        known = dist < MATCH or (dist < LOOSE and margin >= MARGIN)
        out.append(Slot(i, name if known else None, dist, y, crop))
    # the hand is contiguous from slot 0; anything after a hole is not the hand (melds, effects)
    hand = []
    for s in out:
        if s.index != len(hand):
            break
        hand.append(s)
    # the cursor's tile stands clearly higher than the rest (a white tile reads a few pixels high on its own)
    if hand:
        tops = sorted(s.raised for s in hand)
        usual = tops[len(tops) // 2]
        high = min(hand, key=lambda s: s.raised)
        for s in hand:
            s.raised = s is high and usual - s.raised >= 8
    return hand


def counts(slots):
    return engine.parse([s.name for s in slots])


CANCEL_BOX = (1005, 1050, 1750, 1900)  # y0, y1, x0, x1 of "○ 그만두기" under every call/win prompt


def _shape_distance(ink, ref, shifts_y=(-3, 0, 3), shifts_x=(-6, -3, 0, 3, 6)):
    best = 1.0
    for dy in shifts_y:
        for dx in shifts_x:
            r = np.roll(np.roll(ref, dy, axis=0), dx, axis=1)
            best = min(best, 1 - (ink & r).sum() / max(1, (ink | r).sum()))
    return float(best)


_cancel = None


def prompt_visible(img):
    """True when a call/win prompt is up: every one has "○ 그만두기" at the same place, however many
    options are stacked above it."""
    global _cancel
    if _cancel is None:
        _cancel = _ink_bright(_load_png(os.path.join(os.path.dirname(__file__), '..', 'templates', 'prompt',
                                                     '_cancel.png')))
    y0, y1, x0, x1 = CANCEL_BOX
    return _shape_distance(_ink_bright(img[y0:y1, x0:x1]), _cancel) < 0.5


def _ink_bright(crop):
    return crop.min(axis=2) > 200


def selected_option(img):
    """Centre y of the highlighted (dark) option box above the cancel line, or None."""
    band = (img[700:1000, 1650:1800].max(axis=2) < 70).mean(axis=1)
    rows = np.nonzero(band > 0.6)[0]
    if len(rows) < 20:
        return None
    # the longest run of dark rows
    runs, start = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b != a + 1:
            runs.append((start, a))
            start = b
    runs.append((start, rows[-1]))
    a, b = max(runs, key=lambda r: r[1] - r[0])
    return 700 + (a + b) // 2


# ---------------------------------------------------------------- the tile just discarded (for calls)

def _kind(name):
    """Colour family of a tile: what a small, possibly rotated river tile can still be told apart by."""
    if name in ('E', 'S', 'W', 'N', '2p', '4p', '8p'):  # these pins have no red circle
        return 'black'
    if name == 'C':
        return 'red'
    if name == 'F':
        return 'green'
    if name == 'P':
        return 'blank'
    if name.endswith('s'):
        return 'green'
    return 'red+black'  # man and pin


def colours(face):
    """Shares of red, green and dark ink on a tile face crop."""
    f = face.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    red = ((r > 150) & (g < 110) & (b < 120)).mean()
    green = ((g > r + 30) & (g > b + 10) & (g < 200)).mean()
    dark = (f.max(axis=2) < 90).mean()
    return red, green, dark


def tile_face(crop):
    """The white face inside a crop that may include table and tile edges."""
    white = crop.min(axis=2) > 170
    rows = np.nonzero(white.mean(axis=1) > 0.4)[0]
    cols = np.nonzero(white.mean(axis=0) > 0.4)[0]
    if len(rows) < 8 or len(cols) < 8:
        return crop
    return crop[rows[0] + 2:rows[-1] - 1, cols[0] + 2:cols[-1] - 1]


def kind_of(face):
    red, green, dark = colours(tile_face(face))
    if red < 0.01 and green < 0.01 and dark < 0.01:
        return 'blank'
    if green > max(red, dark) and green > 0.02:
        return 'green'
    if red > 0.02 and dark > 0.02:
        return 'red+black'
    if red > 0.02:
        return 'red'
    if dark > 0.02:
        return 'black'
    return None


def new_discard(before, now):
    """Crop of the tile that appeared on the table between two frames (outside the hand row and the
    prompt), or None. Looks for the largest patch of tile-white pixels that changed."""
    changed = np.abs(before.astype(np.int16) - now.astype(np.int16)).max(axis=2) > 60
    changed[880:, :] = False
    changed[900:, 1500:] = False
    changed &= now.min(axis=2) > 170
    if changed.sum() < 300:
        return None
    grid = np.zeros((1080 // 20 + 1, 1920 // 20 + 1), int)
    ys, xs = np.nonzero(changed)
    np.add.at(grid, (ys // 20, xs // 20), 1)
    cy, cx = np.unravel_index(np.argmax(grid), grid.shape)
    # grow a box around the busiest cell over cells that changed too
    y0, y1, x0, x1 = cy, cy, cx, cx
    for _ in range(6):
        if y0 > 0 and grid[y0 - 1, x0:x1 + 1].max() > 40: y0 -= 1
        if y1 < grid.shape[0] - 1 and grid[y1 + 1, x0:x1 + 1].max() > 40: y1 += 1
        if x0 > 0 and grid[y0:y1 + 1, x0 - 1].max() > 40: x0 -= 1
        if x1 < grid.shape[1] - 1 and grid[y0:y1 + 1, x1 + 1].max() > 40: x1 += 1
    return now[y0 * 20:(y1 + 1) * 20, x0 * 20:(x1 + 1) * 20]


def called_tile(before, now, hand_names):
    """Which pair in the hand the prompt is about: the candidates (tiles held twice or more) whose colour
    family matches the new discard. Returns the matching candidate names (one when it is certain)."""
    pairs = sorted({n for n in hand_names if hand_names.count(n) >= 2})
    crop = new_discard(before, now)
    if crop is None:
        return pairs, None
    k = kind_of(crop)
    return [n for n in pairs if _kind(n) == k], k


# ---------------------------------------------------------------- our seat wind

SEAT_BOX = (655, 710, 792, 842)  # y0, y1, x0, x1 of the round wind badge next to our name


def seat_wind(img, folder):
    """'E', 'S', 'W' or 'N' from the badge next to our name; None when no badge is there.
    The West badge has not been seen yet: a badge that matches none of the others is taken as West."""
    y0, y1, x0, x1 = SEAT_BOX
    crop = img[y0:y1, x0:x1].astype(np.int16)
    best, dist = None, 255.0
    for f in glob.glob(os.path.join(folder, '*.png')):
        d = float(np.abs(_load_png(f).astype(np.int16) - crop).mean())
        if d < dist:
            best, dist = os.path.basename(f)[0], d
    if dist < 18:
        return best
    # the badge's dark red ring around a gold letter
    r, g, b = crop[..., 0].mean(), crop[..., 1].mean(), crop[..., 2].mean()
    return 'W' if r > g + 30 and r > b + 30 else None


def score_band(img):
    """True when the dark band of four score plates covers the hand (end of a hand, win or draw)."""
    return (img[850:960].max(axis=2) < 60).mean() > 0.25


# ---------------------------------------------------------------- the word on the call/win prompt

WORD_BOX = (940, 985, 1600, 1840)  # y0, y1, x0, x1 of the word on the prompt
WORDS = {'chi': '치', 'pon': '펑', 'kan': '깡', 'ron': '론', 'tsumo': '쯔모', 'riichi': '리치'}


def _ink(crop):
    return crop.min(axis=2) > 150


def word_crop(img, yc=None):
    """The word on the highlighted option box centred at yc (the single-box position by default)."""
    y0, y1, x0, x1 = WORD_BOX
    if yc is not None:
        y0, y1 = yc - 22, yc + 23
    return img[y0:y1, x0:x1]


def prompt_word(img, folder, yc=None):
    """(key, distance) of the closest saved prompt word ('ron', 'pon', ...) on the highlighted box,
    comparing the bright letter shapes. Distance 0 = same shape, 1 = nothing in common."""
    ink = _ink(word_crop(img, yc))
    best, dist = None, 1.0
    for f in glob.glob(os.path.join(folder, '*.png')):
        key = os.path.splitext(os.path.basename(f))[0]
        if key.startswith('_'):
            continue
        d = _shape_distance(ink, _ink(_load_png(f)), range(-4, 5), range(-6, 7, 2))
        if d < dist:
            best, dist = key, d
    return best, dist
