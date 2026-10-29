# Meadowlark waves-to-volts table, measured on the LC-PolScope (2026-10-28)

`mmgr_dal_MeadowlarkLC_measured_20261028.csv` replaces the retardance-vs-voltage table the
Micro-Manager MeadowlarkLC adapter uses to turn the palette's waves into volts. The stock table's
LC-B column is 0.06-0.08 waves low across LC-B's working range (3.8-5.2 V) and LC-A's about 0.01
low, measured by the LCSWEEP of 2026-10-28 (`lc_sweep_20261028_122830.json`, PolScope Drive
folder). That error is why the LC-B palette looked lopsided (+0.0147 / -0.0287 waves, but
-187 / +211 mV) and why the calibration warned "51% off on the Poincare sphere".

Built by `make_meadowlark_csv.py sweep.json original.csv out.csv` from the stock file
(`OtherDocuments/polscope/mmgr_dal_MeadowlarkLC.csv`):

- the 546 nm block is the measured curve, set so the adapter's interpolation to 549 nm (the
  filter in the beam) gives exactly the measurement;
- the 490 and 630 nm blocks keep the stock file's ratio to 546 nm at their own voltages;
- below the first fringe (about 2 V) the stock shape is kept, scaled to meet the measurement;
- each crystal's extinction fringe (LC-A 7.2 V, LC-B 4.4 V) is bridged by a cubic pinned to the
  fringe, where the fringe reconstruction is least precise.

Checked off the rig: through the new table the adapter's value at every measured point from 3.5
to 9 V matches the sweep to +0.0001 waves on average; the 10-28 palette's drive voltages read
LC-A 0.2519 / LC-B 0.5005 at extinction and +/-0.03 swings that are nearly symmetric.
Below about 1.2 V the columns wiggle as the stock file does; nothing works there.

## Installing (a human decision; nothing does it automatically)

1. Close Micro-Manager. In the Micro-Manager install folder, rename `mmgr_dal_MeadowlarkLC.csv`
   to `mmgr_dal_MeadowlarkLC.stock.csv` (keep it).
2. Copy `mmgr_dal_MeadowlarkLC_measured_20261028.csv` there as `mmgr_dal_MeadowlarkLC.csv`.
3. Start Micro-Manager and the microscope server. Calibrate Liquid Crystals on a clear field,
   Apply, then collect the background: the palette should come out near LC-A 0.25 / LC-B 0.50
   with swing states close to +/-0.03 on both crystals, and the Poincare warning gone.
4. Optional check: Measure LC voltage curves again; the table-vs-measured gap near the palette
   should be under about 0.005 waves.

To undo: put the stock file back under its original name and restart Micro-Manager.
