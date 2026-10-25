"""Demo fixture baseline generator (the frozen starting artifact).

Usage: python -I program.py /absolute/output/dir
Writes the official baseline submission `BASE 100`, which normalizes to
reward ~1.0 under the fixture protocol.
"""
import sys
from pathlib import Path


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    (output / 'submission.npz').write_text('BASE 100\n')
    print('wrote demo baseline submission')


if __name__ == '__main__':
    main()
