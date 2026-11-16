import os, sys, glob
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame
src, out = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(src + '/[0-9][0-9][0-9].png'))
pygame.font.init(); font = pygame.font.Font(None, 40)
for s in range(0, len(files), 16):
    sheet = pygame.Surface((1920, 1080))
    for i, f in enumerate(files[s:s+16]):
        im = pygame.transform.smoothscale(pygame.image.load(f), (480, 270))
        x, y = (i % 4) * 480, (i // 4) * 270
        sheet.blit(im, (x, y))
        sheet.blit(font.render(os.path.basename(f)[:3], True, (255, 255, 0), (0, 0, 0)), (x + 4, y + 4))
    pygame.image.save(sheet, '%s/sheet%02d.png' % (out, s // 16 + 1))
print('sheets', (len(files) + 15) // 16)
