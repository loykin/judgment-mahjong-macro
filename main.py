"""Judgment mahjong: plays hands for the completion list (wins at Lullaby / Modern / Tachibana).

Run from the psconnector-view bar (macro.json), or by hand while psconnector-view is connected:
    .venv/bin/python -u main.py [--dry-run] [--games N]

What it does each moment, from the screen alone:
- a call/win prompt (bottom right): Ron / Tsumo -> accept; Riichi -> accept when the hand is ready;
  Chi / Pon / Kan -> decline (the hand stays closed). An unknown prompt is saved and the macro stops.
- its own turn (closed hand of 14): picks the discard with the lowest shanten and the most useful tiles,
  moves the cursor there and discards.
- a result screen ("× 진행") -> continues; the parlour menu ("게임 시작하기") -> starts the next game.
- a hand tile it does not recognise: saves the picture to unknown/ and stops, so it can be labelled.

--dry-run reads and decides but presses nothing (prints what it would do).
"""
import argparse
import os
import sys
import time

import numpy as np

from mj import engine, record, vision
from psconnector import PS

HERE = os.path.dirname(os.path.abspath(__file__))
UNKNOWN = os.path.join(HERE, 'unknown')
# OCR regions as screen fractions (x0, y0, x1, y1)
FOOTER = (1300 / 1920, 1020 / 1080, 1.0, 1.0)
MENU = (0.3, 0.3, 0.7, 0.62)
RESULT = (464 / 1920, 300 / 1080, 1456 / 1920, 800 / 1080)  # yaku, han and points on a result screen
ROUND = (823 / 1920, 440 / 1080, 1097 / 1920, 500 / 1080)   # "동1국" in the middle of the table
WIND = {'동': 'E', '남': 'S', '서': 'W', '북': 'N'}
DRAGONS = ('P', 'F', 'C')


class Bot:
    def __init__(self, ps, dry_run=False, games=0):
        self.ps, self.dry, self.games_left = ps, dry_run, games
        self.tpl = vision.Templates(os.path.join(HERE, 'templates', 'hand'))
        self.rt = vision.RiverTemplates(os.path.join(HERE, 'templates', 'hand'))
        self.wins = self.discards = 0
        self.riichi = False          # we declared riichi this hand
        self.riichi_pending = False  # accepted the riichi prompt, the discard must keep tenpai
        self.last_names = None
        self.stable = 0
        self.history = []            # recent (time, frame) without a prompt, to see the discard being called
        self.winds = None            # (round wind, seat wind) for this hand
        self.unknown_prompt = 0
        self.last_look = 0.0
        self.lowered = False         # moved the cursor once to read a raised tile it did not know
        self.asked_riichi = False    # pressed □ for riichi this turn
        self.sanshoku_said = False
        self.won_at = 0.0            # when we took a win prompt (its result screen is ours)
        self.win_recorded = True
        self.hand_end_at = 0.0
        self.folded = False

    # ---------------------------------------------------------------- io
    def tap(self, button, hold=0.08):
        if self.dry:
            print(f'  (dry run) {button}')
            return
        self.ps.tap(button, hold=hold)

    def frame(self):
        img = self.ps.frame_array()
        if img.shape[:2] != (1080, 1920):
            raise SystemExit(f'set the picture quality to 1080p (frame is {img.shape[1]}x{img.shape[0]})')
        return img

    def osd(self, text):
        try:
            self.ps.osd(text)
        except Exception:
            pass

    def ocr(self, rel, scale=2.0):
        try:
            return ' '.join(self.ps.ocr(rel=rel, scale=scale))
        except Exception:
            return ''

    def save_unknown(self, img, what):
        os.makedirs(UNKNOWN, exist_ok=True)
        path = os.path.join(UNKNOWN, time.strftime('%Y%m%d-%H%M%S') + f'-{what}.png')
        from PIL import Image
        Image.fromarray(img).save(path)
        return path

    def read_winds(self, img=None):
        if self.winds is None:
            r = self.ocr(ROUND, scale=2.0).replace(' ', '')
            rw = next((WIND[k] for k in WIND if k in r), 'E')
            sw = vision.seat_wind(img if img is not None else self.frame(), os.path.join(HERE, 'templates', 'seat'))
            self.winds = (rw, sw)
            print(f'round wind {rw} ("{r}"), seat wind {sw}')
        return self.winds

    def yakuhai(self, img=None):
        rw, sw = self.read_winds(img)
        return set(DRAGONS) | {rw} | ({sw} if sw else set())

    # ---------------------------------------------------------------- decisions
    def prompt_text(self, img, yc):
        """The word on the highlighted option: matched against saved letter shapes; a new word is read
        with OCR and its shape saved, so it is recognised by shape from then on (OCR misreads single
        syllables, e.g. 론 as 굴)."""
        folder = os.path.join(HERE, 'templates', 'prompt')
        key, dist = vision.prompt_word(img, folder, yc)
        if key and dist < 0.35:
            return vision.WORDS.get(key, key)
        rel = (1600 / 1920, (yc - 25) / 1080, 1840 / 1920, (yc + 25) / 1080)
        text = self.ocr(rel, scale=3.0).replace(' ', '')
        # longest word first: 리치 contains 치
        key = next((k for k, w in sorted(vision.WORDS.items(), key=lambda kv: -len(kv[1])) if w in text), None)
        if key and not os.path.exists(os.path.join(folder, key + '.png')):
            from PIL import Image
            Image.fromarray(vision.word_crop(img, yc)).save(os.path.join(folder, key + '.png'))
            print(f'  learned the prompt word "{text}" as {key}')
        return text

    def wanted(self, word, img, hand):
        """Whether to take this option, and why."""
        if '론' in word or '쯔모' in word:
            return True, 'win'
        if '리치' in word:
            c = vision.counts(hand) if hand and all(s.name for s in hand) else None
            ready = c is not None and sum(c) == 14 and bool(engine.tenpai_discards(c))
            return ready, 'riichi' + ('' if ready else ' (hand not read as ready)')
        if '펑' in word or '퐁' in word:
            # a pon of a value tile (dragons, round or seat wind) gives the hand its yaku
            names = [sl.name for sl in hand if sl.name]
            before = next((f for t, f in reversed(self.history) if time.time() - t > 0.4), None)
            match, kind = vision.called_tile(before, img, names) if before is not None else (None, None)
            values = self.yakuhai(img)
            take = bool(match) and all(n in values for n in match)
            return take, f'pon: new discard looks {kind}, candidates {match}, value tiles {sorted(values)}'
        return False, 'call'

    def on_prompt(self, img, hand):
        """One or more options stacked above "○ 그만두기". Reads the highlighted one, steps down through
        the rest, takes the first one worth taking, otherwise cancels."""
        seen = []
        for _ in range(5):
            yc = vision.selected_option(img)
            if yc is None:
                break
            word = self.prompt_text(img, yc)
            if not word or word in seen:
                break
            seen.append(word)
            take, why = self.wanted(word, img, hand)
            if take:
                print(f'prompt {seen} -> take "{word}" ({why})')
                self.tap('cross')
                if '론' in word or '쯔모' in word:
                    record.bump('ron' if '론' in word else 'tsumo')
                    self.won_at, self.win_recorded = time.time(), False
                    self.wins += 1
                    self.osd(f'화료 {self.wins}')
                    time.sleep(3.0)  # the winning hand is shown open next; not ours to discard from
                elif '리치' in word:
                    record.bump('riichi')
                    self.riichi_pending = True
                elif '펑' in word:
                    record.bump('pons')
                self.unknown_prompt = 0
                time.sleep(0.8)
                return
            if not any(w in word for w in vision.WORDS.values()):
                break  # a word it does not know: do not step past it
            self.tap('down', hold=0.05)
            time.sleep(0.35)
            img = self.frame()
            if not vision.prompt_visible(img):
                return
        known = seen and all(any(w in x for w in vision.WORDS.values()) for x in seen)
        if not known:
            # the box slides in: give it a moment before calling the word unknown
            self.unknown_prompt += 1
            if self.unknown_prompt < 4:
                time.sleep(0.25)
                return
            path = self.save_unknown(img, 'prompt')
            raise SystemExit(f'unknown prompt {seen}, saved {path}; stopping')
        print(f'prompt {seen} -> pass')
        self.tap('circle')
        self.unknown_prompt = 0
        time.sleep(0.8)

    def on_turn(self, hand, img):
        c = vision.counts(hand)
        called = (14 - len(hand)) // 3   # pon/chi already made: 11 tiles in hand = one call
        rivers = vision.read_rivers(img, self.rt)
        visible = list(c)
        for tiles in rivers.values():
            for n, _, _ in tiles:
                visible[engine.INDEX[n]] += 1
        visible = [min(4, v) for v in visible]
        riichi_seats = [st for st in ('right', 'top', 'left') if any(sw for _, sw, _ in rivers[st])]
        indicators = vision.read_dora_indicators(img, self.rt)
        dora = tuple(engine.dora_of(engine.INDEX[n]) for n in indicators)
        target = engine.sanshoku_target(c) if called == 0 else None
        if target and not self.sanshoku_said:
            self.sanshoku_said = True
            print(f'  three-colour straight in reach: keeping {" ".join(engine.NAMES[t] for t in target)}')
        folding = False
        if self.riichi:
            # after riichi the drawn tile goes unless it wins (the win prompt comes first)
            target = len(hand) - 1
            reason = 'riichi: discard the drawn tile'
        else:
            keep = ()
            if self.riichi_pending:
                allowed = set(engine.tenpai_discards(c, called))
                keep = tuple(t for t in range(34) if t not in allowed)
            t, s, u = engine.choose_discard(c, visible=visible, called=called, keep=keep, dora=dora, target=target)
            extra = f', dora {" ".join(engine.NAMES[d] for d in dora)}' if dora else ''
            extra += ', sanshoku' if target else ''
            reason = f'discard {engine.NAMES[t]} (shanten {s} after, {u} useful tiles left{extra})'
            if riichi_seats and not self.riichi_pending and s > 0:
                # someone is in riichi and we are not ready: give up the hand, discard the safest tile
                rivers_ids = [{engine.INDEX[n] for n, _, _ in rivers[st]} for st in riichi_seats]
                t, d, s2 = engine.defensive_discard(c, rivers_ids, visible, called)
                folding = True
                if not self.folded:
                    self.folded = True
                    record.bump('folds')
                reason = f'riichi by {"/".join(riichi_seats)}: fold, discard {engine.NAMES[t]} (danger {d:g})'
            name = engine.NAMES[t]
            # the rightmost copy, so the drawn tile goes when it is the one
            target = max(sl.index for sl in hand if sl.name == name)
        cursor = next((sl.index for sl in hand if sl.raised), None)
        if called == 0 and not self.riichi and not self.riichi_pending and not self.asked_riichi \
                and not folding and engine.tenpai_discards(c):
            # riichi is not offered on its own: □ opens the action commands, where it should be
            self.asked_riichi = True
            print('  ready for riichi: opening the action commands (□)')
            self.tap('square')
            time.sleep(0.8)
            img = self.frame()
            if vision.prompt_visible(img):
                self.on_prompt(img, hand)
                return  # read the hand again: after riichi the discard must keep it ready
            self.tap('square')  # nothing came up: put the commands back as they were
            time.sleep(0.4)
            print(f'  no action command appeared; saved {self.save_unknown(img, "no-riichi")}')
        print(f'hand {" ".join(sl.name for sl in hand)} | cursor {cursor} -> {reason}')
        self.osd(f'{" ".join(sl.name for sl in hand)}\n{reason}')
        if cursor is None:
            self.tap('right')  # wakes the cursor
            return
        for _ in range(16):
            if cursor == target:
                break
            self.tap('right' if target > cursor else 'left', hold=0.05)
            time.sleep(0.12)
            if self.dry:
                cursor += 1 if target > cursor else -1
                continue
            again = vision.hand_slots(self.frame(), self.tpl)
            cursor = next((sl.index for sl in again if sl.raised), cursor)
        if cursor != target:
            print('  cursor did not reach the tile; reading again')
            return
        self.tap('cross')
        self.discards += 1
        self.asked_riichi = False
        if self.riichi_pending:
            self.riichi, self.riichi_pending = True, False
        # wait for the tile to leave the hand
        t0 = time.time()
        while not self.dry and time.time() - t0 < 3:
            time.sleep(0.15)
            now = vision.hand_slots(self.frame(), self.tpl)
            if len(now) % 3 != 2:
                break
        self.last_names, self.stable = None, 0

    def on_other(self, img):
        footer = self.ocr(FOOTER, scale=2.0)
        if '진행' in footer or vision.score_band(img):
            if time.time() - self.hand_end_at > 8:
                record.bump('hands')
            self.hand_end_at = time.time()
            if '진행' in footer and not self.win_recorded and time.time() - self.won_at < 60:
                # our win: keep its yaku and size
                self.win_recorded = True
                lines = self.ps.ocr(rel=RESULT, scale=1.5) if not self.dry else []
                result = record.parse_result(lines)
                os.makedirs(os.path.join(record.LOGS, 'wins'), exist_ok=True)
                shot = os.path.join(record.LOGS, 'wins', time.strftime('%Y%m%d-%H%M%S') + '.jpg')
                from PIL import Image
                Image.fromarray(img).save(shot, quality=85)
                record.record_win(result, os.path.relpath(shot, HERE))
                print(f'our win: {result}')
            print(f'end of hand ({footer or "score plates"}) -> continue')
            self.riichi = self.riichi_pending = False
            self.winds = None
            self.sanshoku_said = False
            self.folded = False
            self.tap('cross')
            time.sleep(1.0)
            return
        menu = self.ocr(MENU, scale=1.5)
        if '게임시작하기' in menu.replace(' ', ''):
            if self.games_left == 1:
                raise SystemExit('played the requested number of games')
            if self.games_left > 1:
                self.games_left -= 1
            print('parlour menu -> start a game')
            record.bump('games')
            self.tap('cross')
            time.sleep(2.0)

    # ---------------------------------------------------------------- loop
    def step(self):
        img = self.frame()
        hand = vision.hand_slots(img, self.tpl)
        # end of a hand first: its dark panels also cover the spot where call prompts appear
        if vision.score_band(img):
            self.on_other(img)
            return
        if vision.prompt_visible(img):
            self.on_prompt(img, hand)
            return
        now = time.time()
        self.history = [(t, f) for t, f in self.history if now - t < 3.0] + [(now, img)]
        if hand and len(hand) % 3 == 2:
            names = [s.name for s in hand]
            if None in names:
                unknown = [sl for sl in hand if sl.name is None]
                if len(unknown) == 1 and unknown[0].raised and not self.lowered:
                    # the cursor's tile is seen at an angle; move the cursor off it and read it lying down
                    self.lowered = True
                    self.tap('left' if unknown[0].index > 0 else 'right', hold=0.05)
                    time.sleep(0.3)
                    return
                # a tile it cannot read: keep the picture for labelling once it held still for a few
                # seconds (a winning draw glows gold until the tsumo prompt comes up)
                self.stable = self.stable + 1 if names == self.last_names else 0
                self.last_names = names
                if self.stable >= 12:
                    path = self.save_unknown(img, 'tile')
                    raise SystemExit(f'unknown tile in the hand {hand}, saved {path}; stopping')
                return
            # act only on a hand read the same twice (not during the draw animation)
            self.stable = self.stable + 1 if names == self.last_names else 0
            self.last_names = names
            if self.stable >= 1:
                self.on_turn(hand, img)
                self.lowered = False
            return
        self.last_names, self.stable = None, 0
        # not our turn: now and then look for menus and result screens (OCR is slow)
        if not hand or time.time() - self.last_look > 2.0:
            self.last_look = time.time()
            self.on_other(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='decide but press nothing')
    ap.add_argument('--games', type=int, default=int(os.environ.get('MJ_GAMES', '0')),
                    help='stop at the parlour menu after this many games (0 = keep going)')
    a = ap.parse_args()
    import signal

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)  # also when started in the background, where SIGINT is ignored
    if not a.dry_run:
        record.start_logging()
    ps = PS()
    bot = Bot(ps, dry_run=a.dry_run, games=a.games)
    print(f'mahjong bot started{" (dry run)" if a.dry_run else ""}')
    try:
        while True:
            if ps.should_stop():
                print('time limit reached')
                break
            bot.step()
            time.sleep(0.15)
    except KeyboardInterrupt:
        print('stopped')
    finally:
        print(f'wins {bot.wins}, discards {bot.discards}')
        bot.osd('')


if __name__ == '__main__':
    sys.exit(main())
