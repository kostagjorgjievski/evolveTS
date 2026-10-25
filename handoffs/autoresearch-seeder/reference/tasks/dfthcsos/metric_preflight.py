"""Use the pinned Kaggle metric's original circuit/NPZ readers unchanged."""
import ast
import math
import pathlib
from typing import Any, Mapping
import zipfile
import numpy as np


def readers(metric_path):
    tree = ast.parse(pathlib.Path(metric_path).read_text())
    names = {'read_circuit', 'read_npz'}
    constants = {'ALLOWED_INSTRUCTIONS', 'MAX_QUBIT_OR_BIT_ID', 'MAX_NPZ_BYTES'}
    nodes = [n for n in tree.body if
             isinstance(n, ast.FunctionDef) and n.name in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    namespace = {'pathlib': pathlib, 'math': math, 'np': np, 'Any': Any, 'Mapping': Mapping, 'zipfile': zipfile}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(metric_path), 'exec'), namespace)
    return namespace['read_circuit'], namespace['read_npz']
