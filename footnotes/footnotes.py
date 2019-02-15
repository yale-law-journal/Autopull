import lxml.etree as ET

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'compat': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'w2010': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'rel': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
}

def ns(prefix, tag_name):
    return '{{{}}}{}'.format(NS[prefix], tag_name)

class Paragraph(object):
    def __init__(self, element):
        assert element.tag == ns('w', 'p')
        self.element = element
        self.runs = [Run(e) for e in self.element.findall('w:r', NS)]

    def text(self):
        return ''.join([r.text() for r in self.runs])

class Run(object):
    def __init__(self, element):
        assert element.tag == ns('w', 'r')
        self.element = element

        props = self.element.findall('w:rPr', NS)
        assert len(props) <= 1
        self.props = props[0] if props else None

    def italics(self):
        return bool(self.props.findall('w:i', NS)) or \
            bool(self.props.findall('w:u', NS))

    def smallcaps(self):
        return bool(self.props.findall('w:smallCaps', NS))

    def text(self):
        text_elem = self.element.findall('w:t', NS)
        return text_elem[0].text if text_elem else ''

class Footnote(object):
    def __init__(self, element):
        assert element.tag == ns('w', 'footnote')
        self.element = element
        self.paras = [Paragraph(e) for e in self.element.findall('w:p', NS)]

    def id(self):
        return int(self.element.get(ns('w', 'id')))

class FootnoteList(object):
    def __init__(self, tree):
        self.tree = tree
        self.root = tree.getroot()

        self.footnotes = [Footnote(elem) for elem in self.root.findall('w:footnote', NS)]
        print("Found {} footnotes.".format(len(self.footnotes)))

    @staticmethod
    def from_file(f):
        return FootnoteList(ET.parse(f))
