"""Official QROM baseline generator; official source is Apache-2.0.

Usage: python -I program.py /absolute/output/dfthcsos
The task runtime makes the pinned official dfthcsos helpers importable.
"""
from pathlib import Path
import shutil
import sys
import dfthcsos
from dfthcsos.example_submission.angle_k_reference_circuit import (
    build_angle_k_family, load_angle_words, write_kmx_family,
)


def main():
    source = Path(dfthcsos.__file__).resolve().parents[2] / 'sample_submission/dfthcsos/submission.npz'
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    circuits = build_angle_k_family(load_angle_words(source), brot=12, batch_size=8)
    write_kmx_family(circuits, output, format='kmb')
    shutil.copyfile(source, output / 'submission.npz')
    print(f'Wrote {len(circuits)} ANGLE circuits and submission.npz')


if __name__ == '__main__':
    main()
