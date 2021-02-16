import argparse
import json
from bluebook.highlight_doc import highlight_doc

parser = argparse.ArgumentParser()
parser.add_argument("file", metavar="FILE", type=str)
parser.add_argument("--json", action="store_true")
args = parser.parse_args()

result = highlight_doc(args.file, console=(not args.json))
if args.json:
    print(json.dumps(result))
