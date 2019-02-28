import bisect
from enum import Enum
import itertools
from nltk.tokenize import PunktSentenceTokenizer
import re

from .text import Range

def normalize(text):
    return text.replace('“', '"').replace('”', '"').replace('\u00A0', ' ')

def relative_offset(offsets, index, offset):
    return offset - (offsets[index - 1] if index > 0 else 0)

class Parseable(object):
    Side = Enum('Side', 'LEFT RIGHT')

    URL_RE = re.compile(r'(?P<url>(http|https|ftp)://[^ \)/]+[^ ]+)[,;\.]?( |$)')

    SIGNAL_UPPER = r'(See|See also|E.g.|Accord|Cf.|Contra|But see|But cf.|See generally|Compare)(, e.g.,)?'
    SIGNAL = r'({upper}|{lower})'.format(upper=SIGNAL_UPPER, lower=SIGNAL_UPPER.lower())

    SOURCE_WORD = r'[A-Z][A-Za-z0-9\.]*'
    CITATION_RE = re.compile(r'([\.,]["”]? |^ ?|{signal} )(?P<cite>[0-9]+ (?P<source>(& |{word} )*{word}) (§§? )?[0-9,]*[0-9])'.format(word=SOURCE_WORD, signal=SIGNAL))

    XREF_RE = re.compile(r'^({signal} )?([Ii]nfra|[Ss]upra)'.format(signal=SIGNAL))
    OPENING_SIGNAL_RE = re.compile(r'^{signal} [A-Z]'.format(signal=SIGNAL))
    SUPRA_RE = re.compile(r'supra note')
    ID_RE = re.compile(r'^({signal} id\.|Id\.)( |$)'.format(signal=SIGNAL))

    CAPITAL_WORDS_RE = re.compile(r'[A-Z][A-Za-z]*[,:;.]? [A-Z]')

    def __init__(self, text_refs):
        self.text_refs = text_refs

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
        if isinstance(key, slice):
            if key.step is not None and key.step != 1:
                raise TypeError('TextObject slice step not supported.')

            start, stop = key.start, key.stop
            if start is None: start = 0
            if start < 0: start += len(self)
            if stop is None: stop = len(self)
            if stop < 0: stop += len(self)

            start_index, start_rel_offset = self._find(start, side=Parseable.Side.RIGHT)
            stop_index, stop_rel_offset = self._find(stop, side=Parseable.Side.LEFT)
            assert stop_index >= start_index

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

    def citation_sentences(self, abbreviations):
        """Attempt to parse the text into a list of citations."""

        text = normalize(str(self))

        tokenizer = PunktSentenceTokenizer()
        first_pass = (Range(*t) for t in tokenizer.span_tokenize(text))

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
        urls = []
        for m in results:
            url = Range.from_match(m, 'url')
            pre = text[0:m.start('url')]
            paren_depth = pre.count('(') - pre.count(')')
            while paren_depth > 0 and text[url.j - 1] == ')':
                url.j -= 1
                paren_depth -= 1
            urls.append(self[url.slice()])

        return urls

    def link_strs(self):
        return [str(r) for r in self.links()]

    def is_new_citation(self):
        text = str(self).strip()

        if Parseable.ID_RE.match(text) or Parseable.XREF_RE.match(text) or Parseable.SUPRA_RE.search(text):
            # print('  X-ref or repeated source.')
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
        match = Parseable.CITATION_RE.search(str(self))
        if match is None:
            return None

        source = match.group('source').strip().replace(' ', '')
        sliced = self[Range.from_match(match, 'cite').slice()]
        return Citation(sliced, source)

class Citation(object):
    def __init__(self, citation, source):
        self.citation = citation
        self.source = source

    def __str__(self):
        return 'Citation: {}'.format(self.citation)

    def __repr__(self):
        return 'Citation({!r})'.format(self.citation)
