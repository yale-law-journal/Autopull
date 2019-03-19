from collections import defaultdict
import itertools
import lxml.etree as ET
import zipfile

from .text import Range, TextRef, Location

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'compat': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'w2010': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'rel': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
}

def ns(prefix, tag_name):
    return '{{{}}}{}'.format(NS[prefix], tag_name)

class Run(object):
    """Represents a <w:r> element, a run of identically-formatted text."""

    def __init__(self, element):
        assert element.tag == ns('w', 'r')
        self.element = element

        self.props = self.element.find('w:rPr', NS)

    def italics(self):
        """Is this text in italics?"""

        return bool(self.props.findall('w:i', NS)) or \
            bool(self.props.findall('w:u', NS))

    def smallcaps(self):
        """Is this text in small caps?"""

        return bool(self.props.findall('w:smallCaps', NS))

    def text(self):
        """Unformatted text for run."""

        text_elem = self.element.findall('.//w:t', NS)
        return text_elem[0].text if text_elem else ''

    def text_refs(self):
        text_elems = self.element.findall('.//w:t', NS)
        return [TextRef(te, Location.TEXT, Range.from_str(te.text)) for te in text_elems]

class Paragraph(object):
    """Represents a <w:r> element, a paragraph."""

    def __init__(self, element):
        assert element.tag == ns('w', 'p')
        self.element = element
        self.runs = [Run(e) for e in self.element.findall('.//w:r', NS)]

    def text(self):
        """Unformatted text for paragraph."""

        return ''.join([r.text() for r in self.runs])

    def text_refs(self):
        return list(itertools.chain.from_iterable(r.text_refs() for r in self.runs))

class Footnote(object):
    def __init__(self, element, number):
        assert element.tag == ns('w', 'footnote')
        self.element = element
        self.number = number
        self.paragraphs = [Paragraph(e) for e in self.element.findall('.//w:p', NS)]

    def internal_id(self):
        """Internal id. Guaranteed to be unique, but not necessarily what you see in the document."""

        return int(self.element.get(ns('w', 'id')))

    def text(self):
        """Unformatted text for footnote."""

        return ''.join([p.text() for p in self.paragraphs])

    def text_refs(self):
        return list(itertools.chain.from_iterable(p.text_refs() for p in self.paragraphs))

class FootnoteList(object):
    def __init__(self, tree):
        self.tree = tree
        self.root = tree.getroot()

        footnote_elements = self.root.findall('.//w:footnote', NS)
        refs = self.root.findall('.//w:footnoteRef', NS)
        id_map = { ref: idx for idx, ref in enumerate(refs, start=1) }
        id_map[None] = 0

        self.footnotes = [Footnote(elem, id_map.get(elem.find('.//w:footnoteRef', NS))) for elem in footnote_elements]
        print("Found {} footnotes.".format(len(self.footnotes)))

    def __iter__(self):
        return iter(self.footnotes)

    @staticmethod
    def from_file(f):
        """Return a FootnoteList from filename or file object."""

        return FootnoteList(ET.parse(f))

    def remove_hyperlinks(self):
        hyperlinks = self.root.findall('.//w:hyperlink', NS)
        for hyper in hyperlinks:
            children = list(hyper)
            parent = hyper.getparent()
            parent_children = list(parent)
            hyper_idx = parent_children.index(hyper)
            parent.remove(hyper)
            for idx, child in enumerate(children):
                parent.insert(hyper_idx + idx, child)

        hyperlink_styles = self.root.findall('.//w:rStyle[@w:val=\'Hyperlink\']', NS)
        for style in hyperlink_styles:
            style.getparent().remove(style)

class Docx(object):
    def __init__(self, filename, mode='r'):
        self.filename = filename
        self.mode = mode
        self.zipf = None
        self.footnotes_xml = None
        self.footnote_list = None

    def __enter__(self):
        self.zipf = zipfile.ZipFile(self.filename)
        self.footnotes_xml = self.zipf.open('word/footnotes.xml', self.mode)
        self.footnote_list = FootnoteList.from_file(self.footnotes_xml)

        return self

    def __exit__(self, typ, value, traceback):
        self.footnotes_xml.close()
        self.zipf.close()
        self.footnote_list = None

    def write(self, new_filename):
        with zipfile.ZipFile(new_filename, 'w') as new_zipf:
            for info in self.zipf.infolist():
                if info.filename == 'word/footnotes.xml':
                    with new_zipf.open(info, 'w') as out:
                        self.footnote_list.tree.write(out, encoding='utf-8')
                else:
                    new_zipf.writestr(info, self.zipf.read(info))
