"""Recognise web/email addresses and map spoken words to displayed text."""

import re


# Bare domains are deliberately limited to common suffixes to avoid treating
# ordinary dotted words, filenames and decimal numbers as links.
ADDRESS_PATTERN = re.compile(
    r"(?<![\w@])(?:"
    r"(?P<email>[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[a-z]{2,63})"
    r"|(?P<url>(?:https?://|www\.)[^\s<>\"*]+"
    r"|(?:[\w-]+\.)+(?:se|com|org|net|nu|io|edu|gov|dk|no|fi|de|uk|eu)"
    r"(?![\w.-])(?:[/?#][^\s<>\"*]*)?)"
    r")", re.IGNORECASE,
)


def addresses(text):
    for match in ADDRESS_PATTERN.finditer(text):
        value = match.group()
        end = match.end()
        while value:
            last = value[-1]
            if last in '.,;:!?\'”’' or (
                last in ')]}' and value.count(last) > value.count({')': '(', ']': '[', '}': '{'}[last])
            ):
                value = value[:-1]
                end -= 1
            else:
                break
        if value:
            yield match.start(), end, 'email' if match.group('email') else 'url'


class SpeechMap:
    """Character mapping independent of XML tags and replacement lengths."""

    def __init__(self):
        self.text = ''
        self.positions = []
        self.search_pos = 0

    def append(self, spoken, start, end=None):
        self.text += spoken
        if end is None:
            self.positions.extend((start + i, start + i + 1) for i in range(len(spoken)))
        else:
            self.positions.extend([(start, end)] * len(spoken))

    def find_word(self, word):
        # re.IGNORECASE preserves offsets even for characters whose lowercase
        # form contains more than one code point.
        match = re.search(re.escape(word), self.text[self.search_pos:], re.IGNORECASE)
        if not word or match is None:
            return None
        start = self.search_pos + match.start()
        end = self.search_pos + match.end()
        self.search_pos = end
        display_start = self.positions[start][0]
        display_end = self.positions[end - 1][1]
        return display_start, display_end - display_start


def transform_plain(text, transform):
    """Apply a text transformation only outside addresses."""
    parts = []
    last = 0
    for start, end, _ in addresses(text):
        parts.extend((transform(text[last:start]), text[start:end]))
        last = end
    parts.append(transform(text[last:]))
    return ''.join(parts)
