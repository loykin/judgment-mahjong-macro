"""What the macro did, kept on disk so it survives the viewer closing.

- logs/YYYY-MM-DD.log: every line the macro prints, with the time
- stats.json: running totals across runs (hands, wins, riichi, folds, ...) and the yaku of our wins
- logs/wins/: the result screen of each of our wins
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(HERE, 'logs')
STATS = os.path.join(HERE, 'stats.json')

# result screen words for a big hand, from the smallest
LIMITS = ['만관', '하네만', '배만', '삼배만', '역만']


class Tee:
    """Sends prints both to the console (the viewer's macro log) and to today's log file."""

    def __init__(self, stream):
        self.stream = stream
        os.makedirs(LOGS, exist_ok=True)
        self.at_line_start = True

    def write(self, text):
        self.stream.write(text)
        path = os.path.join(LOGS, time.strftime('%Y-%m-%d') + '.log')
        with open(path, 'a', encoding='utf-8') as f:
            for part in text.splitlines(keepends=True):
                if self.at_line_start and part.strip():
                    f.write(time.strftime('%H:%M:%S '))
                f.write(part)
                self.at_line_start = part.endswith('\n')
        return len(text)

    def flush(self):
        self.stream.flush()


def start_logging():
    if not isinstance(sys.stdout, Tee):
        sys.stdout = Tee(sys.stdout)


def load():
    try:
        with open(STATS, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def bump(key, by=1):
    s = load()
    s[key] = s.get(key, 0) + by
    s['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(STATS, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    return s[key]


def parse_result(lines):
    """Yaku, han and points from the OCR lines of a result screen."""
    yaku, han, points, limit = [], None, None, None
    for line in lines:
        t = line.replace(' ', '')
        m = re.fullmatch(r'(\d+)번', t)
        if m:
            han = int(m.group(1))
            continue
        m = re.fullmatch(r'([\d,]+)점', t)
        if m:
            points = int(m.group(1).replace(',', ''))
            continue
        m = re.fullmatch(r'(\D+?)(\d+)번', t)
        if m:
            yaku.append(m.group(1))
            continue
        for word in LIMITS:
            if word in t:
                limit = word
    if limit is None and han is not None:
        limit = '하네만' if 6 <= han <= 7 else '만관' if han == 5 else None
    return {'yaku': yaku, 'han': han, 'points': points, 'limit': limit}


def record_win(result, screenshot=None):
    """Adds one of our wins with its yaku and size to stats.json."""
    s = load()
    s['wins'] = s.get('wins', 0) + 1
    for y in result['yaku']:
        s.setdefault('yaku', {})
        s['yaku'][y] = s['yaku'].get(y, 0) + 1
    if result['limit']:
        s.setdefault('limits', {})
        s['limits'][result['limit']] = s['limits'].get(result['limit'], 0) + 1
    s.setdefault('recent_wins', []).append({'time': time.strftime('%Y-%m-%d %H:%M:%S'), **result,
                                            'screen': screenshot})
    s['recent_wins'] = s['recent_wins'][-30:]
    s['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(STATS, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
