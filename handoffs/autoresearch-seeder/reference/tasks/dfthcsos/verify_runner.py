"""Trusted official verification plus unchanged Kaggle input preflight."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from metric_preflight import readers
from dfthcsos.verify import verify, QUBIT_CAP
from dfthcsos.scoreinfra.reference import ORBITALS


def check(directory, metric, shots=64, salt=''):
    read_circuit, read_npz = readers(metric)
    root = Path(directory)
    paths = sorted([*root.glob('angle_k_*.kmb'), *root.glob('angle_k_*.kmx')],
                   key=lambda p: int(p.stem.removeprefix('angle_k_')))
    if not paths or [p.stem for p in paths] != [f'angle_k_{i}' for i in range(len(paths))]:
        raise ValueError('ANGLE files must be numbered consecutively from zero, with no duplicates')
    spec = {'U': ('f', ('R','B',ORBITALS)), 'W': ('f', ('R','B','C')),
            'H2_I': ('f', ('R','C')), 'H1_I': ('f', ()),
            'Hsym_lower': ('f', (ORBITALS*(ORBITALS+1)//2,)), 'tree_edges': ('iu', (ORBITALS-1,2))}
    arrays = read_npz(root/'submission.npz', spec)
    circuits = [read_circuit(p, QUBIT_CAP) for p in paths]
    result = verify(circuits, arrays, tree_edges=arrays['tree_edges'], shots_per_address=shots, salt=salt)
    expected = (ORBITALS + arrays['U'].shape[0]*arrays['U'].shape[1])*shots
    if result.get('verified_shots') != expected:
        raise ValueError('Incomplete official verification')
    return {'official': result, 'validation': {'shots_per_address': shots, 'expected_shots': expected, 'metric_preflight': True}}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--metric', type=Path, required=True)
    parser.add_argument('--shots-per-address', type=int, default=64)
    parser.add_argument('--salt', default='')
    args=parser.parse_args()
    print(json.dumps(check(args.directory,args.metric,args.shots_per_address,args.salt)))
