# -*- coding: utf-8 -*-
"""The section sums of the Gen4 (.jdl) decoder (engine/formats/jd_jdl.py _section_sum): the width of the sections that
are on, and their width x offset, added section by section in a fixed order with element-wise operations, so that
the decoded numbers are the same bits on any computer and with any number of BLAS threads (a matrix product is handed
to BLAS, whose order of summation is its own). Synthetic numbers only.

    python -m pytest -q tests/test_jdl_section_sum.py
"""
from __future__ import annotations

import ast
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import jd_jdl as J  # noqa: E402


def _plain_sum(row, v, order=None) -> float:
    """The sum of the v[j] whose section is on, one Python float added after the other, in the order given (default:
    the order of the sections)."""
    s = 0.0
    for j in (range(len(v)) if order is None else order):
        if row[j]:
            s += float(v[j])
    return s


def test_the_section_sum_is_a_plain_sum_in_the_order_of_the_sections():
    """Bit for bit the sequential sum of Python floats, for any pattern of sections on, any sign and size of the
    terms, no section and no sample; summed in another order the last digits differ, which is what the fixed order
    rules out."""
    rng = np.random.default_rng(3)
    other = 0
    for n, k in ((0, 5), (7, 0), (1, 1), (500, 3), (2000, 13), (300, 40)):
        on = rng.random((n, k)) < 0.7
        v = rng.normal(0, 1, k) * 10.0 ** rng.integers(-6, 7, k)
        got = J._section_sum(on, v)
        want = np.array([_plain_sum(on[i], v) for i in range(n)], float)
        assert got.dtype == np.float64 and got.shape == (n,)
        assert got.tobytes() == want.tobytes(), (n, k)
        back = np.array([_plain_sum(on[i], v, range(k - 1, -1, -1)) for i in range(n)], float)
        other += int((back != want).sum())
    assert other > 0
    # a header of equal sections placed symmetrically about its centre, as a section layout defines one
    k = 12
    w = np.full(k, 9.144 / k)
    y = (np.arange(k) - (k - 1) / 2) * (9.144 / k)
    on = np.ones((4, k), bool)
    on[1, :3] = False
    on[2, 5:] = False
    on[3, :] = False
    width, moment = J._section_sum(on, w), J._section_sum(on, w * y)
    assert width.tobytes() == np.array([_plain_sum(r, w) for r in on]).tobytes()
    assert moment.tobytes() == np.array([_plain_sum(r, w * y) for r in on]).tobytes()
    assert width[3] == 0.0 and moment[3] == 0.0 and not np.signbit(width[3]) and not np.signbit(moment[3])
    # a list and an integer array are taken as they are
    assert J._section_sum([[True, False, True]], [1, 2, 4]).tolist() == [5.0]


def test_the_gen4_decoder_makes_no_matrix_product():
    """No '@', dot, matmul, einsum, inner or tensordot in the decoder: every sum over the sections is _section_sum."""
    path = os.path.join(ROOT, "engine", "formats", "jd_jdl.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    ops = [n.lineno for n in ast.walk(tree)
           if isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, ast.MatMult)]
    assert ops == [], ops
    names = {"dot", "vdot", "matmul", "einsum", "inner", "tensordot"}
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ((isinstance(n.func, ast.Attribute) and n.func.attr in names)
                  or (isinstance(n.func, ast.Name) and n.func.id in names))]
    assert calls == [], calls
    used = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_section_sum"]
    assert len(used) == 4


def test_a_centre_that_is_only_the_noise_of_cancelling_sections_is_zero():
    """Sections placed symmetrically around the header's middle cancel to the float noise of the sum, not to 0: that
    centre is written 0 (it is no lateral offset); a real offset is kept bit for bit, and no section on gives NaN."""
    y = np.array([-4.5, -3.3, -2.1, -0.9, 0.9, 2.1, 3.3, 4.5]) * 0.3048
    w = np.full(8, 0.3048 * 1.2)
    on = np.ones((3, 8), bool)
    on[1, :3] = False                                        # the left sections off: a real offset to the right
    on[2, :] = False                                         # nothing on
    c = J._section_centre(on, w, y)
    raw0 = J._section_sum(on[:1], w * y)[0] / J._section_sum(on[:1], w)[0]
    assert c[0] == 0.0 and not np.signbit(c[0]) and abs(raw0) < J.OFFSET_NOISE_M
    want = J._section_sum(on[1:2], w * y)[0] / J._section_sum(on[1:2], w)[0]
    assert c[1] == want and c[1] > 0.3
    assert np.isnan(c[2])
    odd = np.array([-0.3, -0.1, 0.1, 0.3])                   # a sum that leaves noise (0.1 is no binary fraction)
    c2 = J._section_centre(np.ones((1, 4), bool), np.full(4, 0.7), odd * 3)
    assert c2[0] == 0.0
