import os, sys, glob
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame, numpy as np
S, T = sys.argv[1], sys.argv[2]
X0, PITCH, W, H = 396, 73.5, 66, 90
def load(f): return pygame.surfarray.array3d(pygame.image.load(f)).transpose(1, 0, 2).astype(np.int16)
tpl = [(os.path.basename(f).split('_')[0], load(f)) for f in sorted(glob.glob(T + '/*.png'))]
def crop(a, i):
    x = int(X0 + PITCH * i)
    if x + W > 1920: return None
    col = a[860:960, x + 12:x + W - 12].min(axis=2).mean(axis=1)
    top = next((y for y in range(len(col)) if col[y] > 185), None)
    if top is None: return None
    y = 860 + top
    t = a[y + 2:y + 2 + H, x:x + W]
    if t.shape[:2] != (H, W) or (t.min(axis=2) > 170).mean() < 0.45: return None
    return t, y
def classify(t):
    d = {}
    for n, p in tpl:
        v = np.abs(p - t).mean()
        d[n] = min(d.get(n, 999), v)
    r = sorted(d.items(), key=lambda kv: kv[1])
    return r[0][0], r[0][1], r[1][1] - r[0][1]
stats = []; hands = []
for f in sorted(glob.glob(S + '/mj/[0-9][0-9][0-9].png') + glob.glob(S + '/mj2/[0-9][0-9][0-9].png')):
    a = load(f); hand = []
    for i in range(15):
        c = crop(a, i)
        if c is None: continue
        n, d, m = classify(c[0])
        stats.append((d, m, f, i, n)); hand.append(n if d < 22 else '?')
    hands.append((f.split('/')[-2] + '/' + os.path.basename(f), hand))
ds = np.array([s[0] for s in stats]); ms = np.array([s[1] for s in stats])
print('slots', len(stats), 'best dist p50 %.1f p95 %.1f max %.1f' % tuple(np.percentile(ds, [50, 95, 100])))
print('margin p5 %.1f min %.1f' % (np.percentile(ms, 5), ms.min()))
weak = sorted(stats, key=lambda s: s[1])[:12]
for s in weak: print('low margin %.1f dist %.1f %s slot %d -> %s' % (s[1], s[0], s[2].split('/')[-2:], s[3], s[4]))
for h in hands[30:36] + hands[200:204]: print(h[0], ' '.join(h[1]))
good = [s for s in stats if s[0] < 22]
gm = np.array([s[1] for s in good])
print('accepted', len(good), 'of', len(stats), 'margin min %.1f p1 %.1f p5 %.1f' % (gm.min(), np.percentile(gm, 1), np.percentile(gm, 5)))
for s in sorted(good, key=lambda s: s[1])[:6]: print('closest call %.1f dist %.1f %s slot %d -> %s' % (s[1], s[0], s[2].split('/')[-2:], s[3], s[4]))
mid = [s for s in stats if 22 <= s[0] < 35]
print('in between (22..35):', len(mid))
for s in mid[:8]: print('  %.1f %s slot %d -> %s' % (s[0], s[2].split('/')[-2:], s[3], s[4]))
