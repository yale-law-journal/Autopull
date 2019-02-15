import lxml.etree as ET
import zipfile

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

        text_elem = self.element.findall('w:t', NS)
        return text_elem[0].text if text_elem else ''

class Paragraph(object):
    """Represents a <w:r> element, a paragraph."""

    def __init__(self, element):
        assert element.tag == ns('w', 'p')
        self.element = element
        self.runs = [Run(e) for e in self.element.findall('w:r', NS)]

    def text(self):
        """Unformatted text for paragraph."""

        return ''.join([r.text() for r in self.runs])

class Footnote(object):
    def __init__(self, element):
        assert element.tag == ns('w', 'footnote')
        self.element = element
        self.paragraphs = [Paragraph(e) for e in self.element.findall('w:p', NS)]

    def id(self):
        """Footnote id. Should be the same as the number you see in the document."""

        return int(self.element.get(ns('w', 'id')))

    def text(self):
        """Unformatted text for footnote."""

        return ''.join([p.text() for p in self.paragraphs])

class FootnoteList(object):
    def __init__(self, tree):
        self.tree = tree
        self.root = tree.getroot()

        self.footnotes = [Footnote(elem) for elem in self.root.findall('w:footnote', NS)]
        print("Found {} footnotes.".format(len(self.footnotes)))

    def __iter__(self):
        return iter(self.footnotes)

    @staticmethod
    def from_file(f):
        """Return a FootnoteList from filename or file object."""

        return FootnoteList(ET.parse(f))

    @staticmethod
    def from_docx(filename):
        """Return a FootnoteList from a zipfile name."""

        with zipfile.ZipFile(filename, 'r') as zipf:
            with zipf.open('word/footnotes.xml') as xml_file:
                footnote_list = FootnoteList.from_file(xml_file)

        return footnote_list
