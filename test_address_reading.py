import unittest
import xml.etree.ElementTree as ET

from address_utils import addresses, transform_plain
from markdown_utils import process_markdown


class AddressReadingTests(unittest.TestCase):
    def prepare(self, text, mode="short", voice="sv-SE-MattiasNeural"):
        return process_markdown(text, voice, mode, include_mapping=True)

    def test_detection_and_punctuation(self):
        text = 'Se https://example.com/a_(b)?x=1&y=2. (www.exempel.se), namn+tagg@example.com! exempel.se/slut.'
        values = [text[start:end] for start, end, _ in addresses(text)]
        self.assertEqual(values, ['https://example.com/a_(b)?x=1&y=2', 'www.exempel.se',
                                  'namn+tagg@example.com', 'exempel.se/slut'])
        self.assertEqual(list(addresses('Storgatan 12, 3.14, rapport.pdf och t.ex.')), [])

    def test_spoken_replacements_and_original_display(self):
        text = '  Besök https://example.com/a_b_c?x=1&y=2 eller maila a_b_c@example.com.'
        display, ssml, tags, mapping = self.prepare(text)
        self.assertEqual(display, text)
        self.assertEqual(tags, [])
        spoken = ''.join(ET.fromstring(ssml).itertext())
        self.assertIn('länk finns', spoken)
        self.assertIn('e-postadress finns', spoken)
        self.assertNotIn('example.com', spoken)
        for word in ('Besök', 'länk', 'finns', 'eller', 'maila', 'e-postadress', 'finns'):
            offset, length = mapping.find_word(word)
            expected = ('https://example.com/a_b_c?x=1&y=2' if word == 'länk' or word == 'finns' and offset < text.index('eller')
                        else 'a_b_c@example.com' if word in ('e-postadress', 'finns') else word)
            self.assertEqual(display[offset:offset + length], expected)

    def test_repeated_words_do_not_match_address_contents(self):
        display, _, _, mapping = self.prepare('finns https://example.com/finns finns')
        results = [mapping.find_word(word) for word in ('finns', 'länk', 'finns', 'finns')]
        self.assertEqual(results[0], (0, 5))
        self.assertEqual(results[1], results[2])
        self.assertEqual(results[3], (display.rindex('finns'), 5))

    def test_skip_and_read(self):
        text = 'Före https://example.com efter a@example.com slut'
        display, ssml, _, mapping = self.prepare(text, 'skip')
        self.assertNotIn('example.com', ssml)
        for word in ('Före', 'efter', 'slut'):
            offset, length = mapping.find_word(word)
            self.assertEqual(display[offset:offset + length], word)
        _, ssml, _, mapping = self.prepare(text, 'read')
        self.assertIn('https://example.com', ssml)
        offset, length = mapping.find_word('https')
        self.assertEqual(text[offset:offset + length], 'https')

    def test_markdown_headings_and_styles(self):
        display, ssml, tags, mapping = self.prepare('# www.example.com\n**Maila a@example.com** och *fortsätt*.')
        self.assertEqual(display, 'www.example.com\nMaila a@example.com och fortsätt.')
        self.assertEqual([tag[0] for tag in tags], ['heading', 'bold', 'italic'])
        ET.fromstring(ssml)
        for word in ('länk', 'finns', 'Maila', 'e-postadress', 'finns', 'och', 'fortsätt'):
            result = mapping.find_word(word)
            self.assertIsNotNone(result)
        self.assertEqual(display[result[0]:sum(result)], 'fortsätt')

    def test_abbreviations_do_not_change_addresses(self):
        text = 'obs https://example.com/obs a.obs@example.com obs'
        self.assertEqual(transform_plain(text, lambda value: value.replace('obs', 'observera')),
                         'observera https://example.com/obs a.obs@example.com observera')

    def test_english_voice(self):
        _, ssml, _, _ = self.prepare('www.example.com a@example.com', voice='en-US-JennyNeural')
        self.assertIn('link available', ssml)
        self.assertIn('email address available', ssml)


if __name__ == '__main__':
    unittest.main()
