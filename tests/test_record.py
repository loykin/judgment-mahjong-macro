import unittest

from mj import record


class Result(unittest.TestCase):
    def test_reads_yaku_han_and_points(self):
        r = record.parse_result(['핑후', '1번', '도라 1번', '리치 1번', '일발 1번', '멘젠쯔모 1번', '5 번', '8000 점'])
        self.assertEqual(r['han'], 5)
        self.assertEqual(r['points'], 8000)
        self.assertEqual(r['limit'], '만관')
        self.assertIn('일발', r['yaku'])
        self.assertEqual(record.parse_result(['하네만', '12000 점'])['limit'], '하네만')
        self.assertIsNone(record.parse_result(['핑후 1번', '2 번', '2000 점'])['limit'])
