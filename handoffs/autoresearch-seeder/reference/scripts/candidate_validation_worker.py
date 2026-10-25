"""Fixed entry point; called only by the bound validation MCP server."""
import argparse
import json
from candidate_validation import validate

parser=argparse.ArgumentParser()
parser.add_argument('--attempt',required=True)
parser.add_argument("--diagnostic",action="store_true")
args=parser.parse_args()
print(json.dumps(validate(args.attempt,diagnostic=args.diagnostic)))
