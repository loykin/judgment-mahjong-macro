import os, sys, glob
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame, numpy as np
S = sys.argv[1]; dirs = sys.argv[2:]
X0, PITCH, W, H = 396, 73.5, 66, 90
files = sorted(f for d in dirs for f in glob.glob(S + '/' + d + '/[0-9][0-9][0-9].png'))
uniq = []
def crop(a, i):
    x = int(X0 + PITCH * i)
    if x + W + 8 > 1920: return None
    col = a[860:960, x + 12:x + W - 12].min(axis=2).mean(axis=1)
    top = next((y for y in range(len(col)) if col[y] > 185), None)
    if top is None: return None
    y = 860 + top
    t = a[y + 2:y + 2 + H, x:x + W]
    if t.shape[:2] != (H, W) or (t.min(axis=2) > 170).mean() < 0.45: return None
    return t
for f in files:
    a = pygame.surfarray.array3d(pygame.image.load(f)).transpose(1, 0, 2).astype(np.int16)
    for i in range(15):
        t = crop(a, i)
        if t is None: continue
        best = min(((np.abs(u[0] - t).mean(), u) for u in uniq), default=(99, None), key=lambda p: p[0])
        if best[0] < 16: best[1][1] += 1
        else: uniq.append([t, 1, f.split('/')[-2] + '/' + os.path.basename(f), i])
uniq.sort(key=lambda u: -u[1])
cols = 14; rows = (len(uniq) + cols - 1) // cols
pygame.font.init(); font = pygame.font.Font(None, 22)
surf = pygame.Surface((cols * (W + 8), rows * (H + 22)))
os.makedirs(S + '/tiles2', exist_ok=True)
for k, (t, n, f, i) in enumerate(uniq):
    r, c = divmod(k, cols)
    s = pygame.surfarray.make_surface(t.astype(np.uint8).transpose(1, 0, 2))
    surf.blit(s, (c * (W + 8), r * (H + 22) + 20))
    surf.blit(font.render('%d:%d' % (k, n), True, (255, 255, 0)), (c * (W + 8) + 2, r * (H + 22) + 2))
    pygame.image.save(s, '%s/tiles2/%03d.png' % (S, k))
pygame.image.save(surf, S + '/tiles2_sheet.png')
print(len(files), 'frames', len(uniq), 'unique')
