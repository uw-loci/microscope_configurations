# LLM-authorable microscope config guide

This guide is written for an LLM (and any human) that needs to take a working Micro-Manager system and produce a QPSC configuration for it without reading the Java/Python source. The goal is that if you can run `Configurator.exe` and click through your hardware once, you should be able to hand this guide plus the resulting Micro-Manager config file to an LLM and get back a working QPSC YAML.

QPSC reads three YAML files per scope:

1. **`config_<SCOPE>.yml`** — the primary config. Microscope identity, hardware (objectives + detectors), modalities, acquisition profiles.
2. **`autofocus_<SCOPE>.yml`** — per-objective autofocus hardware parameters (step count, search range, sweep drift check settings) plus a v2 strategy library and per-modality bindings.
3. **`imageprocessing_<SCOPE>.yml`** — optional. Imaging profiles (exposure, gain, white balance) and background correction settings. Can be omitted until you need it.

Shared resources live in `resources_LOCI.yml`. Objective and detector definitions are pulled from there by ID so the same hardware entry can be referenced from multiple scopes.

---

## 1. config_\<SCOPE\>.yml skeleton

```yaml
microscope:
  name: SCOPE_NAME            # e.g. OWS3, CAMM, PPM
  type: Multimodal            # free-text category
  detector_in_use: null       # set at runtime
  objective_in_use: null      # set at runtime
  modality: null              # set at runtime

# Shared hardware, looked up by ID from resources_LOCI.yml.
slide_size_um: { X: 75000, Y: 25000 }    # physical slide dimensions

stage_limits:
  xlimit: { low: -37500, high: 37500 }
  ylimit: { low: -12500, high: 12500 }
  zlimit: { low: -5000, high: 5000 }

available_objectives:
  - 0.5NA_AIR_10x           # IDs resolved via resources_LOCI.yml
  - 1.4NA_OIL_60x

available_detectors:
  - HAMAMATSU_DCAM_01       # IDs resolved via resources_LOCI.yml
```

### Modalities block

Each **modality** is a class of imaging ("brightfield", "widefield fluorescence", "polarized light", "laser scanning"). Add one entry per modality you care about. Every modality has a `type`, an `illumination` block, and optionally a `channels:` library for multi-channel work.

```yaml
modalities:
  Brightfield:
    type: brightfield
    illumination:
      device: DiaLamp           # MM device label
      type: device_property     # or "config_group"
      state_property: State     # what property toggles on/off
      intensity_property: Intensity  # what property sets brightness
      max_intensity: 2100.0
      label: Transmitted lamp

  Fluorescence:
    type: widefield
    illumination:
      device: LappMainBranch1
      type: device_property
      state_property: State
      intensity_property: State
      max_intensity: 1.0
      label: Epi LED

    # Vendor-agnostic multi-channel library. Any MM-controlled illuminator
    # can be described as a list of ConfigGroup presets + direct device
    # property writes. Nothing in QPSC's base layer needs to know what
    # "DLED" or "CoolLED" or "Lumencor" is -- everything goes through MMCore.
    channels:
      - id: DAPI                                  # short, filesystem-safe
        display_name: DAPI (385 nm)               # user-facing
        exposure_ms: 100
        # intensity_property points at the ONE device property that is
        # the "brightness knob" for this channel. The acquisition dialog
        # exposes this as a spinner the user can tweak per-channel.
        intensity_property: { device: DLED, property: Intensity-385nm }
        # ConfigGroup presets applied in order before the snap. Use this
        # for turrets, shutters, light path selectors.
        mm_setup_presets:
          - { group: Filter Turret, preset: Single photon LED-DA FI TR Cy5-B }
        # Raw property writes applied in order before the snap. Use this
        # for vendors that expose wavelength as a property rather than a
        # preset-selectable state.
        device_properties:
          - { device: DLED, property: Intensity-385nm, value: 25 }
          - { device: DLED, property: Intensity-475nm, value: 0 }
          - { device: DLED, property: Intensity-550nm, value: 0 }
          - { device: DLED, property: Intensity-621nm, value: 0 }
        # Optional dumb-sleep fallback for hardware whose isBusy() reports
        # done too early (some serial LED controllers). Only add if you
        # actually see race conditions between property write and snap.
        settle_ms: 50
      - id: FITC
        display_name: FITC (475 nm)
        exposure_ms: 80
        intensity_property: { device: DLED, property: Intensity-475nm }
        mm_setup_presets:
          - { group: Filter Turret, preset: Single photon LED-DA FI TR Cy5-B }
        device_properties:
          - { device: DLED, property: Intensity-385nm, value: 0 }
          - { device: DLED, property: Intensity-475nm, value: 30 }
          - { device: DLED, property: Intensity-550nm, value: 0 }
          - { device: DLED, property: Intensity-621nm, value: 0 }
      # ... TRITC, Cy5 analogous

  BF_IF:
    # Combined brightfield + immunofluorescence on a single-camera scope.
    # The brightfield channel uses the same camera as the IF channels.
    type: widefield
    illumination:
      device: DiaLamp
      type: device_property
      state_property: State
      intensity_property: Intensity
      max_intensity: 2100.0
      label: BF / IF combo
    channels:
      - id: BF
        display_name: Brightfield
        exposure_ms: 5
        # Same mechanism, different device: the BF channel's brightness
        # knob points at the transmitted lamp.
        intensity_property: { device: DiaLamp, property: Intensity }
        mm_setup_presets:
          - { group: Light Path, preset: 3-R100 (BF Camera) }
        device_properties:
          - { device: DiaLamp, property: State, value: 1 }
          - { device: DiaLamp, property: Intensity, value: 500 }
      - id: FITC
        display_name: FITC (475 nm)
        exposure_ms: 80
        intensity_property: { device: DLED, property: Intensity-475nm }
        mm_setup_presets:
          - { group: Light Path, preset: 2-R100 (Epi Camera) }
          - { group: Filter Turret, preset: Single photon LED-DA FI TR Cy5-B }
        device_properties:
          - { device: DiaLamp, property: State, value: 0 }
          - { device: DLED, property: Intensity-475nm, value: 30 }
```

### Acquisition profiles

Profiles pin a modality to a specific objective + detector and declare the final runtime values. The profile name is the **enhanced modality key**: `<ModalityName>_<Objective>`.

```yaml
acquisition_profiles:
  Brightfield_10x:
    modality: Brightfield
    detector: HAMAMATSU_DCAM_01
    objective: 0.5NA_AIR_10x
    mm_setup_presets:
      - { group: Light Path, preset: 3-R100 (BF Camera) }
      - { group: Dia Shutter, preset: Open }
    exposure_ms: 5
    illumination_intensity: 500

  Fluorescence_10x:
    modality: Fluorescence
    detector: HAMAMATSU_DCAM_01
    objective: 0.5NA_AIR_10x
    # Profile-level presets run ONCE before the channel loop. Use for
    # shutters / light paths / channel selectors that DON'T change
    # between channels.
    mm_setup_presets:
      - { group: Light Path, preset: 2-R100 (Epi Camera) }
      - { group: Epi Shutter, preset: Open }
      - { group: 'Epi Channel: Laser/LED (LAPP)', preset: Epi LED (DLEDI) }
    illumination_intensity: 1.0
    # Optional: which channels this profile offers, and per-channel
    # exposure overrides. Omit to use all channels from the modality's
    # library at their default exposure.
    channels: [DAPI, FITC, TRITC, Cy5]
    channel_overrides:
      Cy5:
        exposure_ms: 200     # 10x needs longer Cy5 exposure

  BF_IF_10x:
    modality: BF_IF
    detector: HAMAMATSU_DCAM_01
    objective: 0.5NA_AIR_10x
    mm_setup_presets:
      - { group: Epi Shutter, preset: Open }
    channels: [BF, FITC, TRITC, Cy5]
    channel_overrides:
      BF:
        # Lower intensity for the 10x BF step (calibrated per-objective).
        # This merges into the BF channel's device_properties list,
        # overriding the DiaLamp Intensity value from the library default.
        device_properties:
          - { device: DiaLamp, property: Intensity, value: 70 }
```

### Backward compat

If a Fluorescence profile has **no `channels:` list** AND the modality has **no channel library**, the system falls back to the original single-snap path. This is how brightfield-only and laser-scanning modalities stay unchanged.

---

## 2. autofocus_\<SCOPE\>.yml (schema v2)

Three top-level sections:

```yaml
schema_version: 2

# Per-objective HARDWARE parameters: these are about what the stage and
# objective can safely do. Sample physics (validity gate, brightness
# check) lives in strategies/modalities below.
autofocus_settings:
  - objective: 0.5NA_AIR_10x
    calibrated: true
    n_steps: 9                  # Z positions sampled on initial search
    search_range_um: 15.0       # total Z range in micrometers
    n_tiles: 5                  # AF runs every N tiles
    interp_strength: 100
    interp_kind: quadratic
    score_metric: normalized_variance   # v1 fallback; v2 uses strategy
    texture_threshold: 0.005            # v1 fallback
    tissue_area_threshold: 0.2          # v1 fallback
    sweep_range_um: 12.0                # per-tile drift check range
    sweep_n_steps: 3                    # per-tile drift check steps
    gap_index_multiplier: 3             # force AF after this x n_tiles
    gap_spatial_multiplier: 2.0         # force AF when far from last

# Strategy LIBRARY: named recipes for "is there enough signal?" +
# "focus score function". Each strategy binds validity_check +
# score_metric + failure mode. Write these once per SCOPE; ported
# unchanged across microscopes unless the sample physics genuinely
# differs.
strategies:
  dense_texture:
    description: >
      H&E, IHC, PPM, confluent IF. Texture stddev AND tissue-area
      mask fraction BOTH above threshold.
    score_metric: laplacian_variance
    validity_check: texture_and_area
    validity_params:
      texture_threshold: 0.010
      tissue_area_threshold: 0.200
      rgb_brightness_threshold: 240.0
      tissue_mask_range: [0.10, 0.90]
      median_floor: 15.0
    on_failure: defer

  sparse_signal:
    description: >
      Beads, pollen, scattered FISH spots on dark background. No area
      gate. Validity = count of bright local maxima above adaptive
      (median + k*MAD) background.
    score_metric: laplacian_variance
    validity_check: bright_spot_count
    validity_params:
      spot_sigma_above_bg: 5.0
      spot_min_separation_px: 8
      min_spots: 3
      min_peak_intensity: 20.0
      bright_pixel_floor: 50.0
    on_failure: proceed

  dark_field:
    description: >
      SHG, LSM, dark-field BF. Whole-FOV gradient magnitude.
    score_metric: brenner_gradient
    validity_check: total_gradient_energy
    validity_params:
      min_gradient_energy: 0.002
    on_failure: proceed

  manual_only:
    description: >
      Skip auto entirely; always prompts user.
    score_metric: none
    validity_check: always_false
    validity_params: {}
    on_failure: manual

# Per-modality BINDINGS: which strategy each modality uses. Modality
# keys are matched against the modality name via longest-prefix-wins,
# case-insensitive, so "fluorescence" matches "Fluorescence_10x",
# "Fluorescence_20x", etc. Add one binding per modality prefix the
# scope supports.
modalities:
  bf:
    strategy: dense_texture
  brightfield:
    strategy: dense_texture
  ppm:
    strategy: dense_texture
    overrides:
      validity_params:
        tissue_mask_range: [0.05, 0.95]
        texture_threshold: 0.005
  fl:
    strategy: sparse_signal
    overrides:
      validity_params:
        spot_sigma_above_bg: 4.0
        min_spots: 2
  fluorescence:
    strategy: sparse_signal
  bf_if:
    strategy: dense_texture
    overrides:
      validity_params:
        tissue_area_threshold: 0.10
  lsm:
    strategy: dark_field
  shg:
    strategy: dark_field
  '2p':
    strategy: dark_field
  confocal:
    strategy: dark_field
```

### Rules

- `schema_version: 2` makes the v2 loader active. Without it, every modality gets `dense_texture (v1 compat)` built from the flat fields in `autofocus_settings`.
- Hardware params (per-objective rows) should vary by objective; sample physics params (strategies) should vary by sample type. Don't mix them.
- Modality keys in `modalities:` are matched longest-prefix-wins, case-insensitive. `Fluorescence_10x` matches both `fl` and `fluorescence` — the longer one wins, so `fluorescence` takes effect.
- The `--af-strategy` CLI flag can override any binding at acquisition time; the Advanced panel dropdown in the Java dialogs emits this flag.

---

## 3. Worked examples

### Example A — single LED + filter wheel (Zeiss Colibri style)

```yaml
channels:
  - id: DAPI
    display_name: DAPI
    exposure_ms: 100
    intensity_property: { device: Colibri, property: Intensity-405 }
    mm_setup_presets:
      # The filter wheel changes per channel -- one preset per channel's
      # filter cube position.
      - { group: Reflector, preset: Position 1 - DAPI }
    device_properties:
      - { device: Colibri, property: Intensity-405, value: 30 }
      - { device: Colibri, property: Intensity-488, value: 0 }
```

### Example B — transmitted lamp + epi LEDs (BF + IF combo)

Already shown in the `BF_IF` example above. Key points: the `BF` channel points `intensity_property` at the transmitted lamp, and the IF channels point it at the LED wavelength driver. The light path ConfigGroup is different for BF (camera-side lamp path) vs IF (epi path).

### Example C — multi-channel LED (CoolLED pE-4000, Lumencor Spectra-X)

Same shape as the DLED example: each channel writes intensity to its own wavelength property, zeroing the others. The ConfigGroup presets can be omitted if there's a shared multi-band filter cube (like OWS3) or included if the turret changes per channel.

---

## 4. Validation checklist

After writing the YAML, verify:

1. **QPSC Java can parse it.** Launch QuPath with the QPSC extension and open the BoundingBox workflow. The modality dropdown should list your modalities; selecting Fluorescence should populate the channel picker with your channel IDs.
2. **Python server can parse it.** Run a short dryrun acquisition. Look for the `Autofocus strategy resolved: ...` log line — it should name the strategy you expect for the modality.
3. **Channel hardware state actually changes.** Open Micro-Manager's Device Property Browser during acquisition. For each channel snap, confirm that:
   - The `mm_setup_presets` list is applied (filter turret at the right preset).
   - Only the expected wavelength property is non-zero.
4. **Stitch produces the expected number of channels.** Run a 2x2 tile acquisition, wait for stitch + merge, open the result in QuPath. The image should have N channels matching your selected channel count, not 1.
5. **AF strategy binding actually fires.** Open `tile_measurements.json` after a run and check the `af_strategy` field on each tile -- it should match the binding you configured.

---

## 5. Common mistakes

- **Using camelCase MMCore method names in vendor docs.** Vendor manuals often say `setConfig`, `setProperty`, `waitForDevice`. Pycromanager's MMCore wrapper uses snake_case (`set_config`, `set_property`, `wait_for_device`). QPSC's Java and Python sides both use the snake_case names internally -- but if you're debugging a failing preset, look for `AttributeError: 'mmcorej_CMMCore' object has no attribute 'setConfig'` in the server log.
- **Profile key vs base modality name.** Channel library lookups, AF strategy bindings, and stitcher branch selection all need the *enhanced profile name* (`Fluorescence_10x`), not the base modality name (`Fluorescence`). Use `ObjectiveUtils.createEnhancedFolderName()` from the Java side if you're composing keys in code.
- **Forgetting to restart Pycromanager after changing the MM config.** MMCore caches the config groups at startup; hot-reloading is not reliable. Kill and restart the server when the MM config changes.
- **Using non-ASCII characters in YAML values.** Windows cp1252 encoding will mangle degree signs, mu symbols, and arrows. Use `deg`, `um`, and `->` in all logging strings and comments.
- **Pointing `intensity_property` at a property that isn't in `device_properties`.** The dialog's intensity spinner reads the value from the property write matching the `intensity_property` pair. If they don't match, the spinner shows an empty or zero value.

---

## 6. Related files

- Session summary: `claude-reports/2026-04-14_ows3-widefield-if-session-summary.md`
- AF redesign: `claude-reports/2026-04-13_modality-aware-autofocus-design.md`
- Phase A/B/C/D progress: `claude-reports/2026-04-14_phase-ABCD-progress.md`
- Java-side channel types: `qupath-extension-qpsc/src/main/java/qupath/ext/qpsc/modality/Channel.java`
- Python-side strategy types: `microscope_control/microscope_control/autofocus/strategies.py`
