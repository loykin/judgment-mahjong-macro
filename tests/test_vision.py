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
        for sample, key in (('prompt_chi.png', 'chi'), ('prompt_pon.png', 'pon'), ('prompt_ron.png', 'ron')):
            got, d = vision.prompt_word(load(sample), folder)
            self.assertEqual(got, key)
            self.assertLess(d, 0.05)

    def test_score_plates_on_a_win(self):
        self.assertTrue(vision.score_band(load('result_win.png')))
