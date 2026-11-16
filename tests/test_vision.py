import glob
import os
import unittest

import numpy as np

from mj import vision

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    return vision._load_png(os.path.join(HERE, 'samples', name))


class Hand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = vision.Templates(os.path.join(HERE, 'templates', 'hand'))

    def test_reads_the_hand_in_a_sample(self):
        slots = vision.hand_slots(load('042.png'), self.t)
        self.assertEqual([s.name for s in slots], ['4m', '6m', '8m', '2s', '5s', '6s', '3p', '8p', '9p', 'P', 'C'])
        self.assertEqual([s.index for s in slots if s.raised], [8])

    def test_prompt_box(self):
        self.assertTrue(vision.prompt_visible(load('prompt_chi.png')))
        self.assertFalse(vision.prompt_visible(load('042.png')))


if __name__ == '__main__':
    unittest.main()


class Calls(unittest.TestCase):
    def test_finds_the_east_that_was_just_discarded(self):
        before, now = load('pon_before.png'), load('prompt_pon.png')
        names = ['7m', '7m', '7m', '8m', '8m', '3s', '4s', '3p', '4p', 'E', 'E', 'C', 'C']
        match, kind = vision.called_tile(before, now, names)
        self.assertEqual(kind, 'black')
        self.assertEqual(match, ['E'])

    def test_colour_family_of_every_known_tile(self):
        wrong = []
        for f in sorted(glob.glob(os.path.join(HERE, 'templates', 'hand', '*.png'))):
            name = os.path.basename(f).split('_')[0]
            got = vision.kind_of(vision._load_png(f))
            if got != vision._kind(name):
                wrong.append((name, got))
        self.assertEqual(wrong, [])


class Clutter(unittest.TestCase):
    def test_a_long_discard_row_above_the_hand_does_not_cut_it(self):
        t = vision.Templates(os.path.join(HERE, 'templates', 'hand'))
        slots = vision.hand_slots(load('stuck_slot3.png'), t)
        self.assertEqual(len(slots), 14)
        self.assertEqual(slots[-1].name, 'F')
        self.assertTrue(slots[-1].raised)


class Screens(unittest.TestCase):
    def test_score_plates_after_a_draw(self):
        self.assertTrue(vision.score_band(load('settle_draw.png')))
        self.assertFalse(vision.score_band(load('042.png')))
        self.assertFalse(vision.score_band(load('prompt_pon.png')))


class PromptWords(unittest.TestCase):
    def test_each_saved_prompt_is_read_back(self):
        folder = os.path.join(HERE, 'templates', 'prompt')
        for sample, key in (('prompt_chi.png', 'chi'), ('prompt_pon.png', 'pon'), ('prompt_ron.png', 'ron'),
                            ('prompt_chi_pon.png', 'chi')):
            img = load(sample)
            self.assertTrue(vision.prompt_visible(img), sample)
            got, d = vision.prompt_word(img, folder, vision.selected_option(img))
            self.assertEqual(got, key, sample)
            self.assertLess(d, 0.1)

    def test_no_prompt_elsewhere(self):
        for sample in ('042.png', 'result_win.png', 'settle_draw.png', 'action_menu.png'):
            self.assertFalse(vision.prompt_visible(load(sample)), sample)

    def test_score_plates_on_a_win(self):
        self.assertTrue(vision.score_band(load('result_win.png')))


class Rivers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rt = vision.RiverTemplates(os.path.join(HERE, 'templates', 'hand'))

    def test_reads_every_river_and_who_is_in_riichi(self):
        r = vision.read_rivers(load('prompt_pon.png'), self.rt)
        by_x = lambda seat: [n for n, _, p in sorted(r[seat], key=lambda t: t[2][0])]
        by_y = lambda seat: [n for n, _, p in sorted(r[seat], key=lambda t: t[2][1])]
        self.assertEqual(by_x('top'), ['4p', '1s', '9p', '6m', '3m', '9s'])
        self.assertEqual(by_y('left'), ['F', 'N', '3s', 'P', '2p', 'E'])
        self.assertEqual(by_y('right'), ['3m', '8p', '2p', 'N', 'W', '6m'])
        self.assertEqual(by_x('self'), ['1p', 'S', '1m', '1m', '9p', '8p'])
        self.assertFalse(any(sw for tiles in r.values() for _, sw, _ in tiles))
        late = vision.read_rivers(load('stuck_slot3.png'), self.rt)
        self.assertEqual([n for n, sw, _ in late['right'] if sw], ['5p'])
        self.assertEqual({s: len(t) for s, t in late.items()}, {'self': 13, 'right': 13, 'top': 13, 'left': 13})
