# Microscope Configurations

YAML configuration templates for QPSC microscope systems.

> **Part of the QPSC (QuPath Scope Control) system**
> For complete installation instructions, see: https://github.com/uw-loci/QPSC

## Overview

This repository contains configuration templates and examples for setting up QPSC with various microscope hardware configurations. These files define microscope-specific settings including hardware components, imaging modalities, autofocus parameters, and image processing settings.

## Files

### Configuration Templates

- **`config_template.yml`** - Comprehensive microscope configuration template with examples for all modality types
- **`autofocus_template.yml`** - Autofocus parameter template with detailed documentation
- **`imageprocessing_template.yml`** - Image processing settings template (exposure, gain, white balance)

### Example Configurations

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
   cp config_template.yml config_my_microscope.yml

   # Edit with your hardware settings
   nano config_my_microscope.yml  # or use your preferred editor
   ```

3. **Configure autofocus (optional):**
   ```bash
   cp autofocus_template.yml autofocus_my_microscope.yml
   # Edit autofocus parameters for your objectives
   ```

4. **Configure image processing (optional):**
   ```bash
   cp imageprocessing_template.yml imageprocessing_my_microscope.yml
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

## Configuration Guide

For detailed configuration instructions, see the [QPSC Configuration Guide](https://github.com/uw-loci/QPSC/blob/main/docs/configuration.md).

## Support

- **Issues:** https://github.com/uw-loci/microscope_configurations/issues
- **QPSC Documentation:** https://github.com/uw-loci/QPSC
- **Micro-Manager:** https://micro-manager.org/

## License

MIT License
