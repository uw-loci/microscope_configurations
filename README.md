# Microscope Configurations

YAML configuration templates for QPSC microscope systems.

> **Part of the [QPSC (QuPath Scope Control)](https://github.com/uw-loci/qupath-extension-qpsc) system.**
> For complete installation and setup instructions, see the [QPSC Installation Guide](https://github.com/uw-loci/qupath-extension-qpsc/blob/main/documentation/INSTALLATION.md).

## Overview

This repository contains configuration templates and examples for setting up QPSC with various microscope hardware configurations. These files define microscope-specific settings including hardware components, imaging modalities, autofocus parameters, and image processing settings.

## Files

### Configuration Templates

Located in the `templates/` folder:

- **`templates/config_template.yml`** - Comprehensive microscope configuration template with examples for all modality types
- **`templates/autofocus_template.yml`** - Autofocus parameter template with detailed documentation
- **`templates/imageprocessing_template.yml`** - Image processing settings template (exposure, gain, white balance)

### Example Configurations

Located in the root directory:

- **`config_PPM.yml`** - PPM (Polarized light) microscope example configuration
- **`config_CAMM.yml`** - CAMM (Multi-modal) microscope example configuration

### Resources

- **`resources/resources_LOCI.yml`** - LOCI hardware component lookup tables (objectives, cameras, etc.)

## Usage

### For QPSC Users

**Recommended:** Use the [QPSC installation instructions](https://github.com/uw-loci/QPSC#quick-start) which includes automated setup of configuration templates.

### Manual Setup

1. **Clone this repository:**
   ```bash
   git clone https://github.com/uw-loci/microscope_configurations.git
   cd microscope_configurations
   ```

2. **Copy and customize a template:**
   ```bash
   # Copy the main configuration template
   cp templates/config_template.yml config_my_microscope.yml

   # Edit with your hardware settings
   nano config_my_microscope.yml  # or use your preferred editor
   ```

3. **Configure autofocus (optional):**
   ```bash
   cp templates/autofocus_template.yml autofocus_my_microscope.yml
   # Edit autofocus parameters for your objectives
   ```

4. **Configure image processing (optional):**
   ```bash
   cp templates/imageprocessing_template.yml imageprocessing_my_microscope.yml
   # Edit exposure and gain settings for your camera
   ```

## Configuration Structure

### Main Configuration File (`config_*.yml`)

Defines the complete microscope setup:

```yaml
microscope:
  name: "Your Microscope Name"
  type: "Multimodal"

modalities:
  ppm_20x:
    type: "ppm"
    angles: [0, 45, 90, 135]
    exposure_ms: 50

hardware:
  objectives:
    - id: "LOCI_4x_001"
      pixel_size_xy_um:
        LOCI_CAMERA_001: 1.105
```

### Stage inserts are optional

The `stage.inserts` block (inside `stage:`) is optional. When it is absent,
the Stage Map utility synthesizes a single-slide insert at the center of
`stage.limits` using `slide_size_um` for the slide footprint. Simple setups
that only need a single slide in the middle of the stage can omit the
`stage.inserts` block entirely and rely on the fallback. Multi-slide holders
and scopes with offset apertures still need an explicit `stage.inserts`
calibration.

## Multi-Channel Widefield IF Schema

QPSC supports vendor-agnostic multi-channel widefield immunofluorescence
(IF) and combined brightfield + IF (BF+IF) acquisition on single-camera
scopes. The schema is driven by two Micro-Manager primitives: named
`ConfigGroup` presets and direct device-property writes. The QPSC base
layer reads the YAML and drives any vendor's illumination hardware
uniformly -- no vendor-specific code lives in the Java or Python loops.

For the full design narrative (pipeline, stitching, merge, PPM-parity),
see `QPSC/docs/multichannel-if-overview.md`. This section documents only
the YAML keys that the parser reads.

The canonical parser is
`qupath-extension-qpsc/src/main/java/qupath/ext/qpsc/utilities/MicroscopeConfigManager.java`
(`parseChannel`, `getModalityChannels`, `getProfileChannelIds`,
`getProfileChannelOverrides`, `getChannelsForProfile`,
`mergeDevicePropertyOverrides`). The Python side in
`microscope_command_server/microscope_command_server/acquisition/workflow.py`
(`resolve_channel_plan`, `_merge_device_property_overrides`) mirrors the
same rules.

The working example for everything below is `config_OWS3.yml` -- it has
both a full `Fluorescence` modality (4-channel library) and a full
`BF_IF` modality (5-channel library with BF as the first entry), plus
profile-level overrides including the extended
`channel_overrides.BF.device_properties` tuning on `BF_IF_10x`.

### Channel library (modality level)

Channels live under `modalities.<name>.channels` as an ordered list.
Each entry is fully self-contained: everything that has to be in effect
for the channel to image correctly is listed inside the entry.

| Field              | Type          | Required | Description |
|--------------------|---------------|----------|-------------|
| `id`               | string        | yes      | Channel identifier. Used as the on-disk subdirectory name and as the CLI argument to the server. Must be unique within the modality. |
| `display_name`     | string        | no       | Human-readable label shown in the channel picker UI. Defaults to `id`. |
| `exposure_ms`      | number        | yes      | Default per-channel exposure in milliseconds. Must be numeric; non-numeric entries are skipped with a warning. |
| `mm_setup_presets` | list of maps  | no       | Ordered list of `{ group, preset }` entries. Each applies a Micro-Manager `ConfigGroup` preset via `core.setConfig(group, preset)`. Runs inside the tile loop, every tile. |
| `device_properties`| list of maps  | no       | Ordered list of `{ device, property, value }` entries. Each applies a direct Micro-Manager device-property write via `core.setProperty(device, property, value)`. `value` is always stringified on the Java side, so any MM property type round-trips. |
| `settle_ms`        | number        | no       | Optional dumb-sleep after the presets and properties have been applied, for hardware whose `isBusy()` reports complete too early. Defaults to `0`. |

Notes:

- `display_name` defaults to the channel `id` if omitted.
- Channels with a missing or non-numeric `exposure_ms`, or a missing
  `id`, are dropped at parse time and a warning is logged.
- On scopes where the filter cube never actually changes (for example a
  multi-band dichroic), repeating the cube preset inside every channel
  is redundant but idempotent -- it keeps the schema uniform across
  instruments where the cube does change.

See the `Fluorescence` modality in `config_OWS3.yml` for a four-channel
DAPI / FITC / TRITC / Cy5 library driving a DLED multi-wavelength source.

### Profile selection and overrides

Acquisition profiles consume the modality's channel library via two
optional keys: a subset filter and per-channel overrides.

- `acquisition_profiles.<profile>.channels` -- optional list of channel
  ids. When present, only the listed ids are acquired, in the order
  given. When absent, every channel from the modality library is used
  in library order. Ids not present in the modality library are dropped
  with a warning and the profile still proceeds with the remaining ids.
- `acquisition_profiles.<profile>.channel_overrides` -- optional map
  keyed by channel id. Each value is a sub-map that may contain:
  - `exposure_ms` (number) -- straight scalar override of the library
    default exposure.
  - `device_properties` (list of maps) -- per-channel device-property
    override list with the extended merge schema described below.

Overriding a channel id that is not in the effective selection is a
silent no-op (the override map is only consulted for selected channels).

#### Extended `channel_overrides.<id>.device_properties` merge rule

The override `device_properties` list is merged into the channel's
library `device_properties` list with "replace by (device, property),
append on miss" semantics. For each override entry, in order:

1. Search the channel library's existing `device_properties` for a
   matching `(device, property)` tuple.
2. If matched, replace the value in place, preserving list order.
3. If not matched, append the entry to the end of the list.

This lets a profile tune one property on one channel with a single YAML
line, without having to redeclare the whole channel entry. The exact
same rule is implemented in
`MicroscopeConfigManager.mergeDevicePropertyOverrides` (Java) and
`_merge_device_property_overrides` (Python) and is unit-test-backed on
both sides.

The load-bearing example is the `BF_IF_10x` profile in `config_OWS3.yml`:

```yaml
BF_IF_10x:
  modality: BF_IF
  detector: HAMAMATSU_DCAM_01
  channels: [BF, DAPI, FITC, TRITC, Cy5]
  channel_overrides:
    BF:
      exposure_ms: 20
      device_properties:
        # Replaces the BF channel library's (DiaLamp, Intensity) entry
        # in place. 10x uses a much lower transmitted-lamp intensity
        # than 20x/40x/60x; this single line keeps the per-objective
        # tuning out of the channel library itself.
        - { device: DiaLamp, property: Intensity, value: 70 }
```

### The `bf_if` modality type

`type: bf_if` marks a modality as combined brightfield + widefield
immunofluorescence on a single-camera scope. There is no separate code
path: BF is expressed as a regular entry in the `channels:` library
whose `mm_setup_presets` happen to switch the light path to the
transmitted port and whose `device_properties` happen to drive the
transmitted lamp. The acquisition loop, the stitcher, and the
multichannel merger treat it identically to every fluorescence channel.

The only thing the `bf_if` marker does today is give users a distinct,
discoverable entry in the acquisition UI and give future BF+IF-specific
behavior (image type defaults, background correction strategy) a clear
home without touching the pure-IF handler.

See the `BF_IF` modality and the `BF_IF_10x` / `BF_IF_20x` / `BF_IF_40x`
/ `BF_IF_60x` profiles in `config_OWS3.yml` for the working reference.
Note that BF is the first entry in the library and the `BF_IF_10x`
profile uses the extended `channel_overrides.BF.device_properties` to
drop the transmitted-lamp intensity for the 10x objective.

### Cross-references

- `QPSC/docs/multichannel-if-overview.md` -- cross-repo narrative,
  pipeline diagram, and end-to-end example.
- `qupath-extension-qpsc/documentation/CHANNELS.md` -- Java extension's
  user-facing reference for the channel UI, troubleshooting, and the
  in-process pipeline class names.
- `config_OWS3.yml` -- working reference for both `Fluorescence` and
  `BF_IF` modalities and for the extended
  `channel_overrides.<id>.device_properties` merge.

### Autofocus Configuration (`autofocus_*.yml`)

Defines autofocus parameters per objective:

```yaml
autofocus_settings:
  LOCI_4x_001:
    interp_strength: 3
    score_metric: "NormalizedVariance"
    num_images: 30
    step_size_um: 50
```

### Image Processing Configuration (`imageprocessing_*.yml`)

Defines camera settings per modality and camera:

```yaml
imaging_settings:
  ppm_4x:
    LOCI_CAMERA_001:
      exposure_ms: 50
      gain_dB: 0
```

## Important Notes

- **Do NOT commit your custom configurations to this repository** - The `.gitignore` file excludes all `.yml` files except templates
- **Templates are for reference** - Copy and customize them for your specific hardware
- **LOCI resources** - The `resources/` folder contains shared hardware definitions used across multiple microscopes

## LLM_CONFIG_GUIDE.md sync check

`LLM_CONFIG_GUIDE.md` is the primary reference an LLM (or a human
bootstrapping a new microscope) follows when producing a QPSC config
from scratch. When templates change and the guide doesn't, new scopes
get authored against stale examples and land with subtle schema
mismatches that only show up mid-acquisition.

This repo enforces "template changes must update the guide" in two
layers:

### 1. GitHub Actions workflow (authoritative)

`.github/workflows/guide-sync.yml` runs on every push to `main` and on
every pull request targeting `main`. It:

- **Fails** the check if any file under `templates/` was modified
  without `LLM_CONFIG_GUIDE.md` being touched in the same diff -- this
  blocks merging.
- **Warns** (without failing) when real scope configs
  (`config_OWS3.yml`, `autofocus_PPM.yml`, etc.) are modified without a
  matching guide update.

No setup required -- this runs on GitHub for every contributor
automatically.

### 2. Local pre-commit hook (optional fast-fail)

`githooks/pre-commit` runs the same checks before each local commit so
developers get feedback without waiting for CI. It's opt-in per clone:

```bash
git config core.hooksPath githooks
```

The CI workflow is the line that actually blocks merges; the local hook
just catches the mistake a few seconds earlier. To bypass the local
hook for a single commit (rare), use `git commit --no-verify`. Bypassing
CI is not possible without admin override.

## Configuration Guide

For detailed configuration instructions, see the [QPSC Configuration Guide](https://github.com/uw-loci/QPSC/blob/main/docs/configuration.md).

## Support

- **Issues:** https://github.com/uw-loci/microscope_configurations/issues
- **QPSC Documentation:** https://github.com/uw-loci/QPSC
- **Micro-Manager:** https://micro-manager.org/

## License

MIT License
