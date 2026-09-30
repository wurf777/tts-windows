import unittest
import xml.etree.ElementTree as ET

from address_utils import addresses, transform_plain
from markdown_utils import process_markdown


class PathReadingTests(unittest.TestCase):
    def tokens(self, text):
        return [(text[start:end], kind) for start, end, kind in addresses(text)]

    def prepare(self, text, mode="short", voice="sv-SE-MattiasNeural"):
        return process_markdown(text, voice, mode, include_mapping=True)

    def test_windows_unc_and_relative_paths(self):
        paths = [r'C:\Users\Christian\Documents\rapport.pdf',
                 r'C:/Users/Christian/Documents/rapport.pdf',
                 r'\\server\delning\projekt\rapport.pdf',
                 r'.\projekt\fil.txt', r'..\projekt\fil.txt']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.tokens('Se ' + path + '. Sedan fortsätter vi.'), [(path, 'path')])

    def test_unquoted_windows_spaces_stop_at_filename(self):
        for path in [r'C:\Program Files\TTS Windows\TTS Windows.exe',
                     r'C:\Min mapp\En lång rapport.pdf',
                     r'\\server\Delad mapp\Min rapport.pdf']:
            with self.subTest(path=path):
                self.assertEqual(self.tokens(path + ' och läs sedan nästa mening.'), [(path, 'path')])
                self.assertEqual(self.tokens(path + '. Nästa mening.'), [(path, 'path')])

    def test_quoted_paths_with_spaces(self):
        path = r'C:\Min mapp\En annan mapp'
        for opening, closing in [('"', '"'), ("'", "'"), ('`', '`'), ('“', '”')]:
            with self.subTest(opening=opening):
                text = 'Öppna ' + opening + path + closing + ' och fortsätt.'
                self.assertEqual(self.tokens(text), [(path, 'path')])
                display, ssml, _, mapping = self.prepare(text)
                self.assertEqual(display, text)
                self.assertNotIn('Min mapp', ''.join(ET.fromstring(ssml).itertext()))
                offset, length = mapping.find_word('sökväg')
                self.assertEqual(display[offset:offset + length], path)

    def test_unix_and_home_paths(self):
        for path in ['/Users/me/Documents/rapport.pdf', './folder/report.pdf',
                     '../folder/report.pdf', '~/Documents/report.pdf']:
            self.assertEqual(self.tokens(path + ' efter'), [(path, 'path')])
        self.assertEqual(self.tokens('"/Users/me/Min rapport.pdf"'), [('/Users/me/Min rapport.pdf', 'path')])

    def test_urls_and_emails_inside_paths_are_not_separate_tokens(self):
        text = r'C:\projekt\example.com\a@example.com\fil.txt'
        self.assertEqual(self.tokens(text), [(text, 'path')])
        text = 'https://example.com/users/me/report.pdf'
        self.assertEqual(self.tokens(text), [(text, 'url')])
        self.assertEqual(self.tokens('3/4 2026/09/30 och/eller rapport.pdf Storgatan 12'), [])

    def test_spoken_words_map_to_full_paths_and_following_text(self):
        path = r'C:\projekt\sökväg_finns\example.com\rapport.pdf'
        text = 'finns ' + path + ' finns'
        display, ssml, _, mapping = self.prepare(text)
        self.assertEqual(display, text)
        self.assertEqual(''.join(ET.fromstring(ssml).itertext()), 'finns sökväg finns finns')
        self.assertEqual(mapping.find_word('finns'), (0, 5))
        for word in ('sökväg', 'finns'):
            offset, length = mapping.find_word(word)
            self.assertEqual(display[offset:offset + length], path)
        self.assertEqual(mapping.find_word('finns'), (display.rindex('finns'), 5))

    def test_skip_and_read_modes(self):
        path = r'C:\Users\me\rapport.pdf'
        text = 'Före ' + path + ' efter'
        display, ssml, _, mapping = self.prepare(text, 'skip')
        self.assertNotIn('rapport', ssml)
        for word in ('Före', 'efter'):
            offset, length = mapping.find_word(word)
            self.assertEqual(display[offset:offset + length], word)
        _, ssml, _, _ = self.prepare(text, 'read')
        self.assertIn(path, ''.join(ET.fromstring(ssml).itertext()))

    def test_markdown_and_abbreviations_preserve_path(self):
        path = r'C:\obs\fil_med_understreck.txt'
        text = 'obs ' + path + ' obs'
        self.assertEqual(transform_plain(text, lambda s: s.replace('obs', 'observera')),
                         'observera ' + path + ' observera')
        display, ssml, tags, _ = self.prepare('**Se ' + path + '** och *fortsätt*.')
        self.assertEqual(display, 'Se ' + path + ' och fortsätt.')
        self.assertEqual([tag[0] for tag in tags], ['bold', 'italic'])
        self.assertIn('sökväg finns', ''.join(ET.fromstring(ssml).itertext()))

    def test_english(self):
        _, ssml, _, _ = self.prepare(r'C:\Users\me\file.txt', voice='en-US-JennyNeural')
        self.assertIn('path available', ssml)


if __name__ == '__main__':
    unittest.main()
