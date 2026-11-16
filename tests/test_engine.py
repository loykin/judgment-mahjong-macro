import time
import unittest

from mj import engine as e


class Shanten(unittest.TestCase):
    def s(self, text):
        return e.shanten(e.parse(text))

    def test_complete_and_tenpai(self):
        self.assertEqual(self.s('123m 456p 789s 123s EE'), -1)
        self.assertEqual(self.s('123m 456p 789s 12s EE'), 0)        # waits on 3s
        self.assertEqual(self.s('123m 456p 789s 11s EE'), 0)        # shanpon
        self.assertEqual(self.s('1m 9m 1p 9p 1s 9s ESWNPF C'), 0)   # thirteen orphans, 13-sided
        self.assertEqual(self.s('1122m 3344p 5566s E'), 0)          # seven pairs, waits on E

    def test_far_hands(self):
        self.assertEqual(self.s('147m 258p 369s ESWN'), 6)
        self.assertEqual(self.s('123m 456p 789s 1s 5s E W'), 2)
        self.assertEqual(self.s('123m 456p 789s 13s 5s E'), 1)

    def test_ukeire_counts_unseen_tiles(self):
        hand = e.parse('123m 456p 789s 12s EE')
        self.assertEqual(e.ukeire(hand), {e.INDEX['3s']: 4})
        hand = e.parse('123m 456p 789s 23s EE')
        self.assertEqual(set(e.ukeire(hand)), {e.INDEX['1s'], e.INDEX['4s']})

    def test_discard_keeps_the_best_shape(self):
        # 14 tiles: everything is in shape except the lone North
        hand = e.parse('123m 456p 789s 23s EE N')
        t, s, u = e.choose_discard(hand)
        self.assertEqual((e.NAMES[t], s), ('N', 0))
        self.assertEqual(u, 8)
        # a lone terminal goes before a connected middle tile
        hand = e.parse('123m 456p 34s 67s EE 1p 9m')
        self.assertIn(e.NAMES[e.choose_discard(hand)[0]], ('1p', '9m'))

    def test_riichi_discards(self):
        hand = e.parse('123m 456p 789s 23s EE N')
        self.assertEqual([e.NAMES[t] for t in e.tenpai_discards(hand)], ['N'])

    def test_fast_enough(self):
        hand = e.parse('147m 258p 369s ESWN 5m')
        t0 = time.time()
        e.choose_discard(hand)
        self.assertLess(time.time() - t0, 1.0)


if __name__ == '__main__':
    unittest.main()


class Consistency(unittest.TestCase):
    def test_fourteen_tile_shanten_equals_best_discard(self):
        import random
        rng = random.Random(7)
        wall = [t for t in range(34) for _ in range(4)]
        for _ in range(400):
            hand = rng.sample(wall, 14)
            c = [hand.count(t) for t in range(34)]
            best = min(e.shanten([c[i] - (i == t) for i in range(34)]) for t in range(34) if c[t])
            self.assertEqual(e.shanten(c), best, e.names(c))
            # one more useful tile always lowers shanten by exactly one
            c13 = list(c)
            c13[hand[0]] -= 1
            s = e.shanten(c13)
            for t in e.ukeire(c13):
                c13[t] += 1
                self.assertEqual(e.shanten(c13), s - 1)
                c13[t] -= 1


class Defence(unittest.TestCase):
    def test_genbutsu_beats_everything(self):
        river = {e.INDEX['5m']}
        seen = [0] * 34
        self.assertEqual(e.danger(e.INDEX['5m'], river, seen), 0)
        self.assertLess(e.danger(e.INDEX['2m'], {e.INDEX['5m']}, seen), e.danger(e.INDEX['2p'], river, seen))
        # nakasuji 5s: 2s and 8s gone
        both = {e.INDEX['2s'], e.INDEX['8s']}
        self.assertLess(e.danger(e.INDEX['5s'], both, seen), e.danger(e.INDEX['5s'], {e.INDEX['2s']}, seen))

    def test_folds_with_the_safe_tile(self):
        hand = e.parse('147m 258p 369s ESW 5m')
        river = {e.INDEX['9s']}
        visible = list(hand)
        t, d, s = e.defensive_discard(hand, [river], visible)
        self.assertEqual((e.NAMES[t], d), ('9s', 0.0))


class Value(unittest.TestCase):
    def test_dora_follows_its_indicator(self):
        for ind, dora in (('8m', '9m'), ('9m', '1m'), ('N', 'E'), ('C', 'P'), ('2p', '3p')):
            self.assertEqual(e.NAMES[e.dora_of(e.INDEX[ind])], dora)

    def test_keeps_the_dora_between_equal_tiles(self):
        hand = e.parse('234m 456p 678s 33m 5p 1s 9s')
        self.assertEqual(e.NAMES[e.choose_discard(hand)[0]], '1s')   # the weakest tile, without dora
        t, _, _ = e.choose_discard(hand, dora=(e.INDEX['1s'],))
        self.assertNotEqual(e.NAMES[t], '1s')                        # kept once it is dora

    def test_sanshoku_mode_keeps_the_straight(self):
        hand = e.parse('345m 34p 45s 99m 1p 7s 8s E')
        target = e.sanshoku_target(hand)
        self.assertEqual(sorted(e.NAMES[t] for t in target), sorted(['3m', '4m', '5m', '3p', '4p', '5p', '3s', '4s', '5s']))
        t, _, _ = e.choose_discard(hand, target=target)
        self.assertNotIn(e.NAMES[t], ('3p', '4p', '4s', '5s'))
        self.assertIsNone(e.sanshoku_target(e.parse('147m 258p 369s ESWN')))
