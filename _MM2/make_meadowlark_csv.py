"""Build a corrected mmgr_dal_MeadowlarkLC.csv from an LCSWEEP record (2026-10-28).

The adapter converts waves to volts through a table of retardance (nm) against voltage (mV) at
490, 546 and 630 nm, one block each, interpolating in wavelength. This replaces the 546 nm block
with the sweep's measured curves and scales the 490 / 630 blocks by the original file's own
ratio to 546 at each voltage (keeping its dispersion), so the adapter's value at the measured
wavelength equals the measurement. Below the first fringe the sweep has no data: the original
values are kept, scaled to meet the measurement at the boundary.

Each fringe turning point is bridged by a cubic fit through the data on either side, pinned to
the turning point (its retardance is exact): the fringe reconstruction is least precise there,
and both crystals' extinction points sit on one.

Usage: python3 make_meadowlark_csv.py sweep.json original.csv out.csv
"""

import csv
import json
import sys

import numpy as np


def smooth_curve(curve, landmarks, bridge_v=0.30, fit_v=0.70, exclude_v=0.15):
    v = np.asarray(curve["volts"], float)
    w = np.asarray(curve["waves"], float)
    out = w.copy()
    for lm in landmarks:
        vl, wl = lm["volts"], lm["waves"]
        m = (np.abs(v - vl) <= fit_v) & (np.abs(v - vl) > exclude_v)
        if m.sum() < 6:
            continue
        x = np.concatenate([v[m], [vl] * 20])  # the turning point, weighted heavily
        y = np.concatenate([w[m], [wl] * 20])
        p = np.polyfit(x - vl, y, 3)
        b = np.abs(v - vl) <= bridge_v
        out[b] = np.polyval(p, v[b] - vl)
    # retardance must fall with voltage
    out = np.minimum.accumulate(out)
    return v, out


def main(sweep_path, original_path, out_path):
    s = json.load(open(sweep_path))
    lam = float(s["wavelength_nm"])
    rows = list(csv.reader(open(original_path, encoding="utf-8-sig", newline="")))
    curves = {}
    for ax, col in (("LCA", 0), ("LCB", 1)):
        e = s["axes"][ax]
        curves[col] = smooth_curve(e["curve"], e["landmarks"])
    # data rows: numeric first cell, after the wavelength row "0,490,490,..."
    out_rows = []
    data_started = False
    report = []
    for r in rows:
        if not data_started:
            out_rows.append(r)
            if len(r) >= 9 and r[0].strip() == "0" and r[1].strip() == "490":
                data_started = True
            continue
        if not r or r[0].strip() == "-" or len(r) < 9:
            out_rows.append(r)
            continue
        r = list(r)
        if r[3].strip() == "" or r[6].strip() == "":
            out_rows.append(r)
            continue
        v546 = float(r[3]) / 1000.0
        for col in (0, 1):
            old546 = float(r[4 + col])
            # the 630 block has its own voltage column; interpolate its ratio at this voltage
            vv, mw = curves[col]
            if v546 < vv.min():
                # below the first fringe: keep the old shape, scaled to meet the data
                vb = vv.min()
                scale = (mw[0] * lam) / old_at(rows, 4 + col, vb)
                m_nm = old546 * scale
            else:
                m_nm = float(np.interp(v546, vv, mw)) * lam
            r630 = old_at(rows, 7 + col, v546, vcol=6) / old546 if old546 > 0 else 1.0
            new546 = m_nm / (1.0 + (lam - 546.0) / (630.0 - 546.0) * (r630 - 1.0))
            r[4 + col] = f"{new546:.4f}"
            report.append((col, v546, old546, new546))
        out_rows.append(r)
    # the 630 block keeps its own voltages: rescale it by the 546 change at those voltages
    # keep the original's line endings
    ending = "\r\n" if b"\r\n" in open(original_path, "rb").read() else "\n"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator=ending).writerows(_rescale_others(rows, out_rows))
    return report


def old_at(rows, col, volts, vcol=3):
    """Linear interpolation of an original column at a voltage (V)."""
    xs, ys = [], []
    started = False
    for r in rows:
        if not started:
            if len(r) >= 9 and r[0].strip() == "0" and r[1].strip() == "490":
                started = True
            continue
        if len(r) < 9 or r[0].strip() == "-" or not r[vcol].strip() or not r[col].strip():
            continue
        xs.append(float(r[vcol]) / 1000.0)
        ys.append(float(r[col]))
    xs, ys = np.asarray(xs), np.asarray(ys)
    order = np.argsort(xs)
    return float(np.interp(volts, xs[order], ys[order]))


def _rescale_others(orig, new):
    """Scale each 490 and 630 entry by new546/old546 at that block's OWN voltage.

    The three blocks keep separate voltage columns, and around the file's hand-edited
    anchors their rows do not line up (490 at 2127 mV beside 546 at 2184), so nothing
    may be taken across a row."""
    out = []
    started = False
    for ro, rn in zip(orig, new):
        rn = list(rn)
        if not started:
            out.append(rn)
            if len(ro) >= 9 and ro[0].strip() == "0" and ro[1].strip() == "490":
                started = True
            continue
        if len(ro) >= 9 and ro[0].strip() != "-":
            for vcol in (0, 6):
                if not ro[vcol].strip():
                    continue
                v = float(ro[vcol]) / 1000.0
                for col in (0, 1):
                    o546 = old_at(orig, 4 + col, v)
                    n546 = old_at(new, 4 + col, v)
                    if ro[vcol + 1 + col].strip() and o546 > 0:
                        rn[vcol + 1 + col] = f"{float(ro[vcol + 1 + col]) * n546 / o546:.4f}"
        out.append(rn)
    return out


if __name__ == "__main__":
    main(*sys.argv[1:4])
