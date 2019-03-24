import bisect

from .footnotes import ns, NS
from .text import Range

class Format(object):
    def __init__(self, italics=False, small_caps=False):
        self.italics = italics
        self.small_caps = small_caps

    @staticmethod
    def from_element(element):
        run = None
        for ancestor in element.iterancestors():
            if ancestor.tag == ns('w', 'r'):
                run = ancestor
                break

        if run is None: return None

        return Format(
            italics=bool(ancestor.findall('.//w:i', NS)),
            small_caps=bool(ancestor.findall('.//w:smallCaps', NS)),
        )

    def roman(self):
        return not self.italics and not self.small_caps

class FormatList(object):
    def __init__(self, format_list):
        # List of pairs of (Range, Format)
        self.format_list = format_list

    @staticmethod
    def from_parseable(parseable):
        format_list = []
        position = 0
        for text_ref in parseable.text_refs:
            new_position = position + len(text_ref)
            format_list.append((Range(position, new_position), Format.from_element(text_ref.element)))

        return FormatList(format_list)

    def _positions(self):
        return [r.i for r, _ in self.format_list]

    def find(self, i):
        format_idx = bisect.bisect_left(self._positions(), i)
        return self.format_list[format_idx]

    def __getitem__(self, i):
        if not isinstance(i, int):
            raise TypeError()

        _, formatting = self.find(i)
        return formatting

def extend_front_if_formatted(parseable):
    format_list = FormatList.from_parseable(parseable)
    if format_list[0].roman(): return parseable

    copy = parseable[:]
    first = copy.text_refs[0]
    first.range = Range(0, first.range.j)
    return copy
