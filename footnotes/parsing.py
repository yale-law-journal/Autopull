import bisect
from enum import Enum
import itertools
from os.path import dirname, join
import re

from .text import Range, TextRef

with open(join(dirname(__file__), 'abbreviations.txt'), encoding='utf-8') as f:
    def generate_abbreviations():
        for line in f:
            if line.startswith('#'): continue
            line = line.strip().replace(',', '')
            for word in line.split(' '):
                if word and word.endswith('.'):
                    yield word

    abbreviations = set(generate_abbreviations())
    print("Found {} abbreviations.".format(len(abbreviations)))

NORMALIZATIONS = {
    '“': '"',
    '”': '"',
    '’': '\'',
    '\u00A0': ' ',
}
def normalize(text):
    for sub_out, sub_in in NORMALIZATIONS.items():
        text = text.replace(sub_out, sub_in)

    return text

def relative_offset(offsets, index, offset):
    return offset - (offsets[index - 1] if index > 0 else 0)

class Parseable(object):
    Side = Enum('Side', 'LEFT RIGHT')

    URL_RE = re.compile(r'(?P<url>(http|https|ftp)://[^ \)/]+[^ ]+)[,;\.]?( |$)')

    SIGNAL_UPPER = r'(See|See also|E.g.|Accord|Cf.|Contra|But see|But cf.|See generally|Compare)(, e.g.,)?'
    SIGNAL = r'({upper}|{lower})'.format(upper=SIGNAL_UPPER, lower=SIGNAL_UPPER.lower())

    SOURCE_WORD = '[A-Z][A-Za-z0-9\'\\.]*'
    CITATION_RE = re.compile(r'([\.,]["”]? |^ ?|{signal} )(?P<cite>(?P<volume>[0-9]+) (?P<source>(& |{word} )*{word}) (§§? ?)?[0-9,]*[0-9])'.format(word=SOURCE_WORD, signal=SIGNAL))

    XREF_RE = re.compile(r'^({signal} )?([Ii]nfra|[Ss]upra)'.format(signal=SIGNAL))
    OPENING_SIGNAL_RE = re.compile(r'^{signal} [A-Z]'.format(signal=SIGNAL))
    SUPRA_RE = re.compile(r'supra note')
    ID_RE = re.compile(r'^({signal} id\.|Id\.)([ ,]|$)'.format(signal=SIGNAL))
    HEREINAFTER_RE = re.compile(r'\[hereinafter (?P<hereinafter>[^\]]+)\]')

    CAPITAL_WORDS_RE = re.compile(r'[A-Z0-9][A-Za-z0-9]*[,:;.]? [A-Z0-9]')

    def __init__(self, text_refs):
        if len(text_refs) > 1:
            tr0 = text_refs[0]
            tr1 = text_refs[-1]
            assert tr0.range.j == len(tr0.fulltext())
            assert tr1.range.i == 0
            for tr in text_refs[1:-1]:
                assert tr.range.i == 0
                assert tr.range.j == len(tr.fulltext())

        self.text_refs = text_refs

    @staticmethod
    def from_element(self, element):
        def gather_refs(parent):
            for child in root:
                if len(child.text) > 0:
                    yield TextRef.from_text(child)
                yield from gather_refs(child)

            if len(parent.tail) > 0:
                yield TextRef.from_tail(parent)

        return Parseable(list(gather_refs(element)))

    def __str__(self):
        return ''.join(str(tr) for tr in self.text_refs)

    def __repr__(self):
        return 'TextObject({!r})'.format(self.text_refs)

    def __len__(self):
        return sum(len(tr) for tr in self.text_refs)

    def _offsets(self):
        """Offset of each constituent text ref. The first one is omitted"""

        lengths = (len(tr.range) for tr in self.text_refs)
        offsets = itertools.accumulate(lengths)

        # This should leave one offset behind (the total length)
        return list(offsets)

    def _find(self, offset, side=Side.LEFT):
        """Get (TextRef index, relative offset) for text to left or right of a given offset (insertion point)."""

        offsets = self._offsets()
        if side == Parseable.Side.LEFT:
            index = bisect.bisect_left(offsets, offset)
        else:
            index = bisect.bisect_right(offsets, offset)

        rel_offset = offset - (offsets[index - 1] if index > 0 else 0)
        return index, rel_offset

    def __getitem__(self, key):
        if isinstance(key, int):
            return str(self)[key]
        elif isinstance(key, slice):
            if key.step is not None and key.step != 1:
                raise TypeError('TextObject slice step not supported.')

            start, stop = key.start, key.stop
            if start is None: start = 0
            if start < 0: start += len(self)
            if stop is None: stop = len(self)
            if stop < 0: stop += len(self)

            start_index, start_rel_offset = self._find(start, side=Parseable.Side.RIGHT)
            stop_index, stop_rel_offset = self._find(stop, side=Parseable.Side.LEFT)
            assert start == stop or stop_index >= start_index

            if start == stop:
                return Parseable([])
            else:
                refs = [tr[:] for tr in self.text_refs[start_index:stop_index + 1]]
                refs[-1] = refs[-1][:stop_rel_offset]
                refs[0] = refs[0][start_rel_offset:]

                return Parseable(refs)
        else:
            raise TypeError('TextObject indices must be slices.')

    def find(self, offset, side=Side.LEFT):
        """Get (TextRef, relative offset) for text to left or right of a given offset (insertion point)."""

        index, rel_offset = self._find(offset, side)
        return self.text_refs[index], rel_offset

    def insert(self, offset, s, side=Side.LEFT):
        """Insert string `s` at `offset` into this object's underlying XML."""

        text_ref, rel_offset = self.find(offset, side)
        if side == Parseable.Side.LEFT:
            return text_ref.insert(rel_offset, s)

    def insert_after(self, s):
        return self.insert(len(self), s, side=Parseable.Side.LEFT)

    def citation_sentences(self, abbreviations=abbreviations):
        """Attempt to parse the text into a list of citations."""

        text = normalize(str(self))
        # print(text)

        def tokens(text):
            periods = re.finditer(r'\. +(?! )', text)
            start = 0
            while start < len(text) and text[start] == ' ':
                start += 1

            for match in periods:
                yield Range(start, match.start(0) + 1)
                start = match.end(0)

            if start < len(text):
                yield Range(start, len(text))

        first_pass = tokens(text)

        # Split at any end paren followed by a capital letter.
        def paren_cap(tokens):
            result = []
            for t in tokens:
                last_index = t.i
                for match in re.finditer(r'\) [A-Z]', str(self[t.slice()])):
                    yield Range(last_index, match.end() - 2)
                    last_index = match.end() - 1
                yield Range(last_index, t.j)

        second_pass = paren_cap(first_pass)

        compacted = []
        for candidate in second_pass:
            if not compacted:
                compacted.append(candidate)
            else:
                last = text[compacted[-1].slice()]
                addition = text[candidate.slice()]
                # print('Last: [{}], Add: [{}]'.format(last, addition))
                _, _, last_word = last.rpartition(' ')
                next_word, _, following = addition.partition(' ')
                paren_depth = last.count('(') - last.count(')')
                bracket_depth = last.count('[') - last.count(']')
                quote_depth = last.count('"') % 2
                if (last_word in abbreviations
                        or addition in abbreviations
                        or (next_word in abbreviations and following in abbreviations)
                        or not addition[0].isupper()
                        or paren_depth > 0
                        or bracket_depth > 0
                        or quote_depth > 0):
                    compacted[-1].combine(candidate)
                else:
                    compacted.append(candidate)

        split = itertools.chain.from_iterable(t.split(text, '; ') for t in compacted)

        return [self[t.slice()] for t in split]

    def links(self):
        text = str(self)
        results = Parseable.URL_RE.finditer(text)
        for m in results:
            url = Range.from_match(m, 'url')
            pre = text[0:m.start('url')]

            # Sometimes people put links in parentheses. Work around that.
            paren_depth = pre.count('(') - pre.count(')')
            while paren_depth > 0 and text[url.j - 1] == ')':
                url.j -= 1
                paren_depth -= 1

            # URLs shouldn't end with a period or semicolon.
            if text[url.j - 1] in [';', '.', ',']:
                url.j -= 1

            yield (url, self[url.slice()])

    def link_strs(self):
        return [str(r) for _, r in self.links()]

    def is_new_citation(self, hereinafters=[]):
        text = str(self).strip()

        if Parseable.XREF_RE.match(text) or Parseable.SUPRA_RE.search(text):
            # print('  X-ref or repeated source.')
            return False

        for h in hereinafters:
            if h in text:
                return False

        hereinafter_match = Parseable.HEREINAFTER_RE.search(text)
        if hereinafter_match:
            hereinafters.append(hereinafter_match.group('hereinafter'))

        if Parseable.ID_RE.match(text) and '§' not in text:
            return False

        if not re.search(r'[0-9]', text):
            return False

        if Parseable.OPENING_SIGNAL_RE.match(text):
            # print('  Opening signal!')
            return True

        if Parseable.CAPITAL_WORDS_RE.search(text):
            # print('  Capital words!')
            return True

        if self.links():
            # print('  Link!')
            return True

        return False

    def citation(self):
        match = Parseable.CITATION_RE.search(normalize(str(self)))
        if match is None:
            return None

        sliced = self[Range.from_match(match, 'cite').slice()]
        volume = int(match.group('volume').strip())
        source = match.group('source').strip().replace(' ', '')
        subdivisions = str(self)[match.end('source'):].strip()
        return Citation(sliced, volume, source, subdivisions)

class Subdivisions(object):
    """Parse Bluebook subdivision ranges."""

    Type = Enum('Type', 'PAGE SECTION PARAGRAPH')

    # Some common sections look like ranges - for example, 42 USC 2000e-2 (meat of Title VII).
    # So we have to be careful to avoid confusing the two.
    DASHES = r'[-–—]'
    TO = r' +to +'
    SECTION_NODASH = r'[0-9][0-9a-zA-Z\.]*'
    SECTION = SECTION_NODASH + '(-[0-9]+)*'
    SUBSECTION = r'(\([A-Za-z0-9]+\))+'
    SECTIONS_GENERIC = r'{sec}({sub})?({range}({sec}|{sub}))?(, ?({sec}{sub}|{sec}|{sub})({range}({sec}|{sub}))?)*'
    SECTIONS_DASH_RE = re.compile(SECTIONS_GENERIC.format(sec=SECTION, sub=SUBSECTION, range=TO))
    SECTIONS_NODASH_RE = re.compile(SECTIONS_GENERIC.format(sec=SECTION_NODASH, sub=SUBSECTION, range=DASHES))

    PAGES_RE = re.compile(r'[0-9]+|[ixv]+')

    def __init__(self, sub_type, ranges):
        self.sub_type = sub_type
        self.ranges = ranges
        # print(self)

    @staticmethod
    def from_str(subdivisions_str):
        # print(subdivisions_str)
        subdivisions_str = subdivisions_str.strip()

        if subdivisions_str.startswith('§'):
            sub_type = Subdivisions.Type.SECTION
        elif subdivisions_str.startswith('¶'):
            sub_type = Subdivisions.Type.PARAGRAPH
        else:
            sub_type = Subdivisions.Type.PAGE

        if sub_type == Subdivisions.Type.PAGE:
            page = Subdivisions.PAGES_RE.match(subdivisions_str.strip())
            if page:
                return Subdivisions(sub_type, [(page.group(0), None)])
        else:
            clean = subdivisions_str.replace('§', '').strip()
            match_dash = Subdivisions.SECTIONS_DASH_RE.match(clean)
            match_nodash = Subdivisions.SECTIONS_NODASH_RE.match(clean)
            if match_nodash:
                dash = False
                separator = Subdivisions.DASHES
                ranges = match_nodash.group(0)
            elif match_dash:
                dash = True
                separator = Subdivisions.TO
                ranges = match_dash.group(0)
            else:
                return Subdivisions(sub_type, [])

            def generate_ranges():
                split = (g.strip() for g in ranges.split(','))
                prev_resolved = None
                for group in split:
                    elements = re.split(separator, group)
                    if len(elements) == 1:
                        low = elements[0]
                        high = None
                    else:
                        low = elements[0]
                        high = elements[1]

                    if prev_resolved is not None and re.match(r'^[\.\(-]', low):
                        # E.g.: 213(a)(15), (b)(21)
                        first_char = low[0]
                        context, _, _ = prev_resolved.partition(first_char)
                        low = context + low

                    if high is not None and high.isdigit() and len(high) < len(low):
                        # E.g.: 306-07
                        high = low[:-len(high)] + high
                    elif high is not None and re.match(r'^[\.\(-]', high):
                        # E.g.: 213(a)-(c)
                        first_char = high[0]
                        context, _, _ = low.partition(first_char)
                        high = context + high

                    yield (low, high)
                    prev_resolved = low

            return Subdivisions(sub_type, list(generate_ranges()))

    def __str__(self):
        range_list = ', '.join('{}-{}'.format(lo, hi) if hi is not None else lo for lo, hi in self.ranges)
        return 'Subdivisions: {}'.format(range_list)

    def __repr__(self):
        return 'Subdivisions({!r}, {!r})'.format(self.sub_type, self.ranges)

class Citation(object):
    def __init__(self, citation, volume, source, subdivisions_str):
        self.citation = citation
        self.volume = volume
        self.source = source
        if subdivisions_str is not None:
            self.subdivisions = Subdivisions.from_str(subdivisions_str)
        else:
            self.subdivisions = None

    def __str__(self):
        return 'Citation: {}'.format(self.citation)

    def __repr__(self):
        return 'Citation({!r})'.format(self.citation)
