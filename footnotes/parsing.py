import itertools
from nltk.tokenize import PunktSentenceTokenizer

from .lib import cached_property

def normalize(text):
    return text.replace('“', '"').replace('”', '"')

class Token(object):
    def __init__(self, i, j):
        self.i = i
        self.j = j

    def slice(self, text):
        return text[self.i:self.j]

    def combine(self, next):
        self.j = next.j

    def split(self, text, separator):
        start_idx = self.i
        tokens = []
        while True:
            end_idx = text.find(separator, start_idx, self.j)
            if end_idx < 0:
                tokens.append(Token(start_idx, self.j))
                break
            tokens.append(Token(start_idx, end_idx + len(separator)))
            start_idx = end_idx + len(separator)

        return tokens

class Paragraph(object):
    def __init__(self, text):
        self.text = normalize(text).strip()

    def citation_sentences(self, abbreviations):
        tokenizer = PunktSentenceTokenizer()
        first_pass = [Token(*t) for t in tokenizer.span_tokenize(self.text)]

        split = itertools.chain.from_iterable(t.split(self.text, '; ') for t in first_pass)

        compacted = []
        for token in split:
            if not compacted:
                compacted.append(token)
            else:
                last = compacted[-1].slice(self.text)
                addition = token.slice(self.text)
                _, _, last_word = last.rpartition(' ')
                paren_depth = last.count('(') - last.count(')')
                bracket_depth = last.count('[') - last.count(']')
                quote_depth = last.count('"') % 2
                if (last_word in abbreviations
                        or not addition[0].isupper()
                        or paren_depth > 0
                        or bracket_depth > 0
                        or quote_depth > 0):
                    compacted[-1].combine(token)
                else:
                    compacted.append(token)

        return [Sentence(t.slice(self.text)) for t in compacted]

class Sentence(object):
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text
