# Fork status and build notes

Updated October 24, 2026. Start with the [ordering BOM](BOM.md).

Available design tools: Fusion 360 and SolidWorks. New mechanical designs should retain editable native source, dimensioned assembly/interface information and STEP exports alongside print meshes. The prototype bench supply, PLA/PETG/TPU and X1 Carbon are available; the Pi model needs confirmation. Team kit count remains unspecified.

## Selected starting point

This fork starts at AI-FanGe/Microduck-build-tutorial commit `49678215d0b40529522772a40c06c216390449dd`. The reference hardware is Pi Zero 2 W, OpenRB-150, BNO08x and fourteen XL330-M288-T servos, with an optional fifteenth beak servo. It supplies a printable Bambu project, deployment source and a walking ONNX file. The upstream real-robot media is evidence of the author's build, not of ours.

Fanduck remains a reference. Inspection of its internal maker-package BOM found the product runtime and a complete replacement body-IMU/power solution excluded. XGO-Duck has matched Feetech software and hardware files, but unfinished hardware licensing and manufacturing-output issues. Dukki's Unitree rework is still in development. The tutorial is our reference prototype, not an already validated team kit.

## What changed in this fork

- English is the default README. The original Chinese text is retained in `README.zh-CN.md`.
- Ordering quantities, included motor accessories, supplier links and lead-time limits are recorded in `BOM.md`.
- Startup loads the policy before enabling motor torque. Cleanup attempts torque-off before input/controller teardown and continues remaining cleanup if an individual action fails. Hardware-free failure-injection tests verify API calls and ordering; they cannot prove torque-off delivery over a real bus.
- A standard-library 3MF audit tool inventories plates, objects, transforms and profiles. Optional small-part STL exports preserve scale and orientation. This is numerical inspection, not a slicer or mechanical-fit certification.

## X1 Carbon print reference

The real print project is the root `microduck3D打印.3mf`; the README's former `microduck/cad/` path was deleted upstream. The file contains five plates, 67 build objects and 65 assigned print instances. Two extra idle-horn objects sit offplate. The saved machine is P1S/0.4 mm, with 21 PLA filament entries, 0.2 mm layers, 2 walls, 15% infill and automatic tree support. These are inherited settings, not an approved X1C profile.

Open it in Bambu Studio, select the actual X1 Carbon/nozzle/plate, remap used filament entries to the installed AMS slots, and reslice. Keep scale at 100%. Use separate soft-part prints if required; ordinary soft TPU should not be assumed compatible with the AMS. We have not sliced, printed or physically fitted these parts. Single-part envelopes fit the X1C's nominal build volume, but that alone says nothing about plate placement, supports, tolerances or strength.

First fit candidates are source object IDs 57 (`idle_horn.stl`), 59 (`idle_cap.stl`), 53 (22 mm ring with an unhelpful upstream OBJ name), and 50 (small plate with an opening). Establish their actual assembly function before treating the printed discs as servo drive horns. Fit one set against actual components before a full print run.

```sh
python3 scripts/audit_print_project.py --output /tmp/microduck-print-audit.json
python3 scripts/audit_print_project.py --export-fit-stls /tmp/microduck-first-fit
```

The tool refuses unsupported external build-item paths and mirrored STL exports rather than silently producing incorrect geometry. Exported geometry inherits the source's rights; the export tool grants no new rights to it.

## Electrical and runtime checks still required

1. Retail XL330 supply limits are 3.7–6.0 V; manufacturer recommends 5 V. Start a single-servo bench at regulated 5.0 V. The tutorial's nominal 6 V pack description is not a defined supply design. Check the actual loaded rail and transients before every expansion of the load. [Motor specification](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/).
2. OpenRB's DXL rail is rated for 3 A. Whole-robot servo power requires a separately rated distribution path, common signal ground and reviewed isolation/backfeed arrangement. [Controller specification](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/).
3. The runtime simulation/current proxy sets `BAM_VIN=7.5`; recovered historical training samples 7–8 V. Those values are modeling assumptions, not measurements of the author's physical supply. Validate or retrain for the regulated rail. We have not established that the bundled walking policy transfers at 5 V.
4. Retain manufacturer protection settings during commissioning. A model-based total-current proxy is not a physical fuse or measured supply current. Measured runtime current/voltage polling is disabled by default, and stale IMU handling still needs review before untethered walking.
5. Record each servo ID, firmware, gains, zero, direction and limits; the inherited ±45-degree knee offsets and IMU orientation are assembly-specific. Do not assume these are calibration data for our robot.
6. Python cleanup cannot guarantee a stopped robot after power loss, SIGKILL, transport failure or default SIGTERM termination. Commission with physical motor-power isolation available.

## Reproducibility gaps

The current training package imports a deleted `robot/` directory. Its 104 historical files are available at `9a11a406a73c8d809daf6de939ef4df3f19f1656`, but have not been restored: their voltage assumptions and mechanical/model compatibility need reconciliation. The runtime's simulation model is not a direct replacement. Do not call the training checkout runnable as-is.

Both package metadata files reference deleted READMEs; no lockfile is tracked despite the setup command using `uv sync --frozen`. A training dependency also follows a moving branch. The linked upstream SD image predates our changes and has not been downloaded or verified in this work. Source/package/image pinning and clean provisioning remain kit-release work.

Before team kits, record the source/image/policy hashes, firmware/configuration, full quantity BOM, labelled harness drawings, source-to-part naming, X1C profile, printed-part weights, calibrated mechanical zeros and independent assembly acceptance. Prove one prototype and then a second independently assembled unit before bulk ordering.

## Licences and original hardware work

Keep existing notices. Root `LICENSE` is MIT; `microduck/LICENSE` identifies GPLv3 control software and CC BY-NC-SA hardware, and the control source headers say GPL-3.0-or-later. The training directory has Apache-2.0. The root 3MF has blank embedded origin/licence metadata, so exact mechanical provenance still requires reconciliation; the root MIT label does not establish permissive rights to all its geometry.

No-sale distribution and company promotional use are different questions under a non-commercial licence. [Creative Commons explains that the purpose of the use matters](https://creativecommons.org/faq/#does-my-use-violate-the-noncommercial-clause-of-the-licenses). Do not represent the existing meshes as an unrestricted promotional kit. Our future hardware can be independently designed with explicit source licences and provenance. Merely converting or redrawing inherited meshes does not establish independence.

Contributions can be prepared as focused, attributed commits for upstream to cherry-pick. This project uses dedicated branches and direct integration into this fork's `main`; pull requests are prohibited by the user's integration policy. No upstream messages or submissions have been sent.

## Desktop verification

Run `uv run --isolated --no-project --python 3.12 python -m unittest discover -s tests -v` from the repository root. On October 24 all 14 tests passed: six print-inventory/export cases and eight startup/cleanup failure-injection cases. `git diff --check` also passed. The print tool was independently reviewed; unsupported mirrored exports and external build paths now fail explicitly.

An additional CPU-only check with ONNX Runtime 1.26.0 and NumPy 2.3.5 loaded `microduck/src/agents/walk.onnx`, confirmed input `obs [1,51]` and output `actions [1,14]`, verified its joint-order metadata against the runtime's observation order, and produced finite outputs for a zero input. This is a model-loading check; zero input is not a physical walking test. No motor, IMU, printed part, supply rail or training run has been tested.
