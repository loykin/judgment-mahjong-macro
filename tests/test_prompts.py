import unittest
from unittest import mock

import main
from mj import vision


class FakeMenu:
    """A stacked prompt: ↓/↑ move the highlight (no wrap), × takes it, ○ cancels."""

    def __init__(self, words):
        self.words, self.at, self.taken, self.cancelled = words, 0, None, False

    def tap(self, button, hold=0.08):
        if button == 'down':
            self.at = min(self.at + 1, len(self.words) - 1)
        elif button == 'up':
            self.at = max(self.at - 1, 0)
        elif button == 'cross':
            self.taken = self.words[self.at]
        elif button == 'circle':
            self.cancelled = True

    def osd(self, *_):
        pass


def bot_for(menu, ready=True):
    b = main.Bot.__new__(main.Bot)
    b.ps, b.dry = menu, False
    b.unknown_prompt, b.history, b.wins = 0, [], 0
    b.riichi_pending = b.open_riichi = False
    b.highlighted = lambda img: menu.words[menu.at]
    b.frame = lambda: None
    b.tap = menu.tap
    b.osd = lambda *_: None
    b.wanted_ready = ready
    return b


class Prompts(unittest.TestCase):
    def run_menu(self, words, ready=True):
        menu = FakeMenu(words)
        b = bot_for(menu, ready)
        tiles = ['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', 'E', 'E', '1p', '1p', 'N']
        hand = [mock.Mock(name=n) for n in tiles]
        for h, n in zip(hand, tiles):
            h.name = n
        with mock.patch.object(vision, 'prompt_visible', return_value=True), \
             mock.patch.object(main.time, 'sleep'), mock.patch.object(main.record, 'bump'):
            b.on_prompt(None, hand if ready else hand[:-1])
        return menu, b

    def test_open_riichi_beats_riichi_even_when_listed_second(self):
        menu, b = self.run_menu(['리치', '오픈리치'])
        self.assertEqual(menu.taken, '오픈리치')
        self.assertTrue(b.open_riichi and b.riichi_pending)

    def test_goes_back_up_to_the_best_option(self):
        menu, _ = self.run_menu(['오픈리치', '리치', '깡'])
        self.assertEqual(menu.taken, '오픈리치')

    def test_a_win_is_taken_at_once(self):
        menu, _ = self.run_menu(['쯔모', '리치'])
        self.assertEqual(menu.taken, '쯔모')

    def test_nothing_worth_taking_is_cancelled(self):
        menu, _ = self.run_menu(['치', '깡'])
        self.assertIsNone(menu.taken)
        self.assertTrue(menu.cancelled)


if __name__ == '__main__':
    unittest.main()
