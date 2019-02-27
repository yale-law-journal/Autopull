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

    CITATION_RE = re.compile(r'(, |^ ?)(?P<cite>[0-9]+ (?P<source>(& |([A-Z][A-Za-z\.]*\.? ))+)[0-9]+)')

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
            refs[0].range.i = start_rel_offset
            refs[-1].range.j = stop_rel_offset

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

        compacted = []
        for candidate in first_pass:
            if not compacted:
                compacted.append(candidate)
            else:
                last = text[compacted[-1].slice()]
                addition = text[candidate.slice()]
                _, _, last_word = last.rpartition(' ')
                paren_depth = last.count('(') - last.count(')')
                bracket_depth = last.count('[') - last.count(']')
                quote_depth = last.count('"') % 2
                if (last_word in abbreviations
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

    def citation(self, reporters=set()):
        match = Parseable.CITATION_RE.search(str(self))
        if match is None:
            return None

        source = match.group('source').strip().replace(' ', '')
        sliced = self[Range.from_match(match, 'cite').slice()]
        if source in reporters:
            return ReporterCitation(sliced)
        else:
            return Citation(sliced)

class Citation(object):
    def __init__(self, citation):
        self.citation = citation

    def __str__(self):
        return 'Citation: {}'.format(self.citation)

    def __repr__(self):
        return 'Citation({!r})'.format(self.citation)

class ReporterCitation(Citation):
    def __repr__(self):
        return 'ReporterCitation({!r})'.format(self.citation)

    def __str__(self):
        return 'Reporter citation: {}'.format(self.citation)
