"""Riichi mahjong hand evaluation: shanten, useful tiles (ukeire) and which tile to discard.

Tiles are indices 0..33: 0-8 man 1-9, 9-17 pin 1-9, 18-26 sou 1-9, 27-30 East South West North,
31-33 White Green Red. Names like '5m', '3p', '7s', 'E', 'P' (white), 'F' (green), 'C' (red) are used
for reading and printing.

Shanten: how many tiles away from tenpai (0 = tenpai, -1 = a complete hand). Computed for the standard
form (4 melds + pair), seven pairs and thirteen orphans; the smallest counts.
"""
from functools import lru_cache

NAMES = [f'{n}{s}' for s in 'mps' for n in range(1, 10)] + ['E', 'S', 'W', 'N', 'P', 'F', 'C']
INDEX = {n: i for i, n in enumerate(NAMES)}
TERMINALS_HONORS = [0, 8, 9, 17, 18, 26] + list(range(27, 34))


def parse(text):
    """'123m 456p EE' or a list of names -> counts[34]."""
    counts = [0] * 34
    items = text if isinstance(text, (list, tuple)) else _expand(text)
    for name in items:
        counts[INDEX[name]] += 1
    return counts


def _expand(text):
    out = []
    for group in text.split():
        if group[-1] in 'mps' and group[:-1].isdigit():
            out += [d + group[-1] for d in group[:-1]]
        else:
            out += list(group)
    return out


def names(counts):
    return [NAMES[i] for i in range(34) for _ in range(counts[i])]


@lru_cache(maxsize=None)
def _suit(counts):
    """Best (melds, partial sets) splits of one suit's 9 counts, as a tuple of non-dominated pairs.
    Partial sets are pairs and two-tile sequence shapes; pairs are also returned separately by the caller."""
    counts = list(counts)
    results = set()

    def go(i, melds, partials):
        while i < 9 and counts[i] == 0:
            i += 1
        if i >= 9:
            results.add((melds, partials))
            return
        # triplet
        if counts[i] >= 3:
            counts[i] -= 3
            go(i, melds + 1, partials)
            counts[i] += 3
        # sequence
        if i <= 6 and counts[i + 1] and counts[i + 2]:
            for k in (i, i + 1, i + 2):
                counts[k] -= 1
            go(i, melds + 1, partials)
            for k in (i, i + 1, i + 2):
                counts[k] += 1
        # partial: pair, adjacent, one-gap
        if counts[i] >= 2:
            counts[i] -= 2
            go(i, melds, partials + 1)
            counts[i] += 2
        if i <= 7 and counts[i + 1]:
            counts[i] -= 1
            counts[i + 1] -= 1
            go(i, melds, partials + 1)
            counts[i] += 1
            counts[i + 1] += 1
        if i <= 6 and counts[i + 2]:
            counts[i] -= 1
            counts[i + 2] -= 1
            go(i, melds, partials + 1)
            counts[i] += 1
            counts[i + 2] += 1
        # leave it as a lone tile
        counts[i] -= 1
        go(i, melds, partials)
        counts[i] += 1

    go(0, 0, 0)
    # keep only splits that are not worse in both numbers than another
    best = [r for r in results if not any(o != r and o[0] >= r[0] and o[1] >= r[1] for o in results)]
    return tuple(best)


def _honors(counts):
    melds = sum(1 for c in counts if c >= 3)
    pairs = sum(1 for c in counts if c == 2)
    return ((melds, pairs),)


def _shanten_exact(counts, called):
    """Standard-form shanten (4 melds + a pair), trying each possible pair explicitly."""
    best = 8
    for pair in [None] + [i for i in range(34) if counts[i] >= 2]:
        c = list(counts)
        if pair is not None:
            c[pair] -= 2
        melds = partials = 0
        options = [_suit(tuple(c[s:s + 9])) for s in (0, 9, 18)] + [_honors(c[27:])]
        # choose per suit to maximise 2*melds + partials (with the 4-set cap applied at the end)
        totals = {(0, 0)}
        for opt in options:
            totals = {(a + m, b + p) for a, b in totals for m, p in opt}
        for m, p in totals:
            m2 = m + called
            p2 = min(p, 4 - m2)
            s = 8 - 2 * m2 - p2 - (1 if pair is not None else 0)
            best = min(best, s)
    return best


def shanten_chiitoi(counts):
    pairs = sum(1 for c in counts if c >= 2)
    kinds = sum(1 for c in counts if c >= 1)
    return 6 - pairs + max(0, 7 - kinds)


def shanten_kokushi(counts):
    kinds = sum(1 for i in TERMINALS_HONORS if counts[i])
    pair = any(counts[i] >= 2 for i in TERMINALS_HONORS)
    return 13 - kinds - (1 if pair else 0)


def shanten(counts, called=0):
    s = _shanten_exact(counts, called)
    if called == 0 and sum(counts) >= 13:
        s = min(s, shanten_chiitoi(counts), shanten_kokushi(counts))
    return s


def ukeire(counts, visible=None, called=0):
    """Tiles that lower the shanten of a 13-tile (mod 3 == 1) hand, and how many of each are left."""
    base = shanten(counts, called)
    seen = visible or counts
    out = {}
    for t in range(34):
        left = 4 - seen[t]
        if left <= 0:
            continue
        counts[t] += 1
        if shanten(counts, called) < base:
            out[t] = left
        counts[t] -= 1
    return out


def _isolation(counts, t):
    """How useless a tile is on its own: honors and terminals with no neighbours first."""
    if counts[t] >= 2:
        return 0
    if t >= 27:
        return 3
    pos = t % 9
    near = sum(counts[t + d] for d in (-2, -1, 1, 2) if 0 <= pos + d <= 8)
    edge = 1 if pos in (0, 8) else 0
    return (2 if near == 0 else 0) + edge


def choose_discard(counts, visible=None, called=0, keep=(), dora=(), target=None):
    """Best tile to discard from a 14-tile hand: lowest shanten after it, then the most useful tiles left
    weighted by what the hand is worth (dora, tanyao, a targeted three-colour straight), then the more
    isolated tile. Returns (tile, shanten_after, ukeire_count)."""
    best = None
    for t in range(34):
        if counts[t] == 0 or t in keep:
            continue
        counts[t] -= 1
        s = shanten(counts, called)
        u = sum(ukeire(counts, visible, called).values())
        worth = u * value(counts, dora, target)
        counts[t] += 1
        key = (s, -worth, -u, -_isolation(counts, t))
        if best is None or key < best[0]:
            best = (key, t, s, u)
    _, t, s, u = best
    return t, s, u


def tenpai_discards(counts, called=0):
    """Tiles whose discard leaves the hand in tenpai (for riichi)."""
    out = []
    for t in range(34):
        if counts[t]:
            counts[t] -= 1
            if shanten(counts, called) == 0:
                out.append(t)
            counts[t] += 1
    return out


# ---------------------------------------------------------------- defence against a riichi

def danger(t, river, visible):
    """How likely discarding tile t deals into a riichi player whose discards are `river` (tile ids),
    on a rough 0..8 scale. visible[t]: copies of t that can be seen (all rivers and our hand)."""
    if t in river:
        return 0.0                      # genbutsu: they cannot ron on a tile they discarded
    if t >= 27:
        seen = visible[t]
        return 1.0 if seen >= 3 else 1.5 if seen == 2 else 2.5 if seen == 1 else 3.5
    n, base = t % 9 + 1, t - t % 9
    low = n - 3 >= 1 and (base + n - 4) in river    # n-3 discarded
    high = n + 3 <= 9 and (base + n + 2) in river   # n+3 discarded
    if n in (1, 9):
        return 2.0 if (high or low) else 4.5
    if n in (2, 8):
        return 2.5 if (high or low) else 5.5
    if n in (3, 7):
        return 3.0 if (high or low) else 6.5
    if low and high:
        return 3.5                      # nakasuji: both sides covered
    return 5.0 if (low or high) else 8.0


def defensive_discard(counts, riichi_rivers, visible, called=0):
    """The safest tile to discard against one or more riichi players (by the most dangerous of them),
    keeping the hand as good as possible among equally safe tiles. Returns (tile, danger, shanten_after)."""
    best = None
    for t in range(34):
        if counts[t] == 0:
            continue
        d = max(danger(t, r, visible) for r in riichi_rivers)
        counts[t] -= 1
        s = shanten(counts, called)
        u = sum(ukeire(counts, visible, called).values())
        counts[t] += 1
        key = (d, s, -u)
        if best is None or key < best[0]:
            best = (key, t, d, s)
    _, t, d, s = best
    return t, d, s


# ---------------------------------------------------------------- hand value: dora, tanyao, sanshoku

def dora_of(indicator):
    """The dora a dora indicator points to."""
    if indicator < 27:
        return indicator - indicator % 9 + (indicator % 9 + 1) % 9
    if indicator < 31:
        return 27 + (indicator - 27 + 1) % 4
    return 31 + (indicator - 31 + 1) % 3


def sanshoku_target(counts, need=6):
    """Tiles of the most complete three-colour straight (n, n+1, n+2 in all three suits) when at least
    `need` of its 9 kinds are already held; else None."""
    best = None
    for n in range(7):
        tiles = [s * 9 + n + k for s in range(3) for k in range(3)]
        have = sum(1 for t in tiles if counts[t])
        if have >= need and (best is None or have > best[0]):
            best = (have, tuple(tiles))
    return best[1] if best else None


def value(counts, dora=(), target=None):
    """A multiplier for how much a hand is worth chasing: dora kept, tanyao still possible, progress
    toward a three-colour straight (when one is targeted)."""
    v = 1.0 + 0.3 * sum(counts[d] for d in dora)
    if not any(counts[t] for t in TERMINALS_HONORS):
        v += 0.3
    if target:
        v += 3.0 * sum(1 for t in target if counts[t]) / len(target)
    return v
