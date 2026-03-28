# Overview

This repository provides an integration between Hubspace and Home Assistant. Due to the cloud-first
nature of Hubspace devices, an internet connection needs to be available, along with the Hubspace servers.

## Supported Devices

A supported device indicates that is maps into Home Assistant. Please note that not all
devices will correctly map and may require further troubleshooting. The supported Devices
are as follows:

- Fan

  - On/Off
  - Speed
  - Preset mode

- Freezer

  - Error sensors
  - Freezer target temperature
  - Fridge target temperature
  - Mode
  - Temperature units
  - Super cold toggle
  - Super cold completion sensors

- Lock

  - Lock / Unlock

- Light

  - On/Off
  - Color Temperature
  - Color Sequences
  - Dimming
  - RGB

- Outlet

  - On/Off

- Portable AC

  - HVAC Mode
  - Fan Mode
  - Temperature
  - Target Temperature

- Smart Glass

  - On/Off

- Switch

  - On/Off

- Thermostat

  - HVAC Mode
  - Fan Mode
  - Temperature
  - Target Temperature

- Transformer

  - On/Off

- Water Valve

  - Open / Close

## Releases

GitHub Releases are the source of truth for version history for this fork:

- https://github.com/SenexCrenshaw/Hubspace-Homeassistant/releases

Recent 6.1.x highlights:

- full freezer controls for targets, mode, units, super-cold, and related status sensors
- freezer-focused automation blueprints for alerts, super-cold cycles, and temporary temperature profiles
- a `Hubspace Freezers` sidebar page for controlling freezer entities from one place in Home Assistant

## Installation

Add this repo as a custom repository in [HACS](https://hacs.xyz/). Add the hubspace integration.

Clicking this badge should add the repo for you:
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SenexCrenshaw&repository=Hubspace-Homeassistant&category=integration)

## Configuration

After Hubspace has been added through HACs, the
configuration continues within the UI like other integrations. First select `Settings`
on the navigation bar, then select `Devices & services`, ensure you are on the
`Integrations` tab, then finally select `ADD INTEGRATION` at the bottom right
of the page. Search for `Hubspace` and enter your username and password and
click `SUBMIT`. Entities should start appearing shortly after clicking submit.

After discovered, the poll time can be configured for quicker or longer
polling intervals. By default, Hubspace is polled once every 30 seconds.

## Freezer Panel

The integration adds a `Hubspace Freezers` sidebar page in Home Assistant. The
page groups each freezer's existing Home Assistant entities into one place so
you can adjust target temperatures, mode, temperature units, and super-cold
from the UI without
digging through entity lists.

Restart Home Assistant after installing or upgrading the integration so the
latest panel frontend module is loaded.

The panel reuses the same entities created by the integration, so controls on
that page call the normal Home Assistant services for:

- `number.*_freezer_target_temperature`
- `number.*_fridge_target_temperature`
- `select.*_mode`
- `select.*_temperature_units`
- `switch.*_super_cold`

## Automation Blueprints

This repo includes optional freezer-focused automation blueprints for Home Assistant `2025.7`
and newer. HACS does not install or update these blueprints for you. Import them manually
from the GitHub file URL, and re-import them later if you want blueprint updates from this repo.

Import path in Home Assistant:

- `Settings -> Automations & scenes -> Blueprints -> Import Blueprint`

Available blueprints:

- [Freezer safety alerts](./blueprints/automation/hubspace/freezer_safety_alerts.yaml)

  - Watches Hubspace freezer alert binary sensors and runs alert and clear actions.
  - Expected entities: freezer high temp alert, fridge high temp alert, sensor failure, MCU communication failure binary sensors.
  - Import URL: `https://raw.githubusercontent.com/SenexCrenshaw/Hubspace-Homeassistant/main/blueprints/automation/hubspace/freezer_safety_alerts.yaml`

- [Freezer super cold cycle](./blueprints/automation/hubspace/freezer_super_cold_cycle.yaml)

  - Starts the Hubspace super-cold switch from any trigger and optionally reports completion or timeout.
  - Expected entities: `switch.*_super_cold`, optional `sensor.*_freezer_super_cold_status`, optional `sensor.*_refrigerator_super_cold_status`.
  - Import URL: `https://raw.githubusercontent.com/SenexCrenshaw/Hubspace-Homeassistant/main/blueprints/automation/hubspace/freezer_super_cold_cycle.yaml`

- [Freezer temperature profile](./blueprints/automation/hubspace/freezer_temperature_profile.yaml)

  - Applies temporary freezer and optional fridge target temperatures, then restores the previous values.
  - Expected entities: `number.*_freezer_target_temperature`, optional `number.*_fridge_target_temperature`.
  - Import URL: `https://raw.githubusercontent.com/SenexCrenshaw/Hubspace-Homeassistant/main/blueprints/automation/hubspace/freezer_temperature_profile.yaml`

Notes:

- these blueprints are optional helpers; they do not add or change Hubspace entities
- blueprint updates are manual re-imports; HACS will continue to manage only the integration itself
- imported blueprints can be customized per automation from the Home Assistant UI after import
- replace `main` in the import URL with a release tag such as `6.1.5` if you want a version-pinned import instead of tracking the latest blueprint revision

## Release Workflow

Use the make targets below to bump the version in
`custom_components/hubspace/manifest.json`, create a release commit,
create an annotated git tag, and publish a GitHub release.
The bump commands stage the current repo changes automatically before
creating the release commit. If nothing else changed, the release commit
contains just the version bump.

```bash
make qa
make test
make lint
make release-patch
make release-minor
make release VERSION=6.1.1
make publish-current
make release-patch GH_RELEASE=0
```

Notes:

- run `make qa` before cutting a release if you want the same basic local checks as CI
- push is on by default; `DRY_RUN=1` suppresses push unless you explicitly set `PUSH=1`
- GitHub release creation is on by default; set `GH_RELEASE=0` if you explicitly want to skip publishing a GitHub release
- `make release-patch`, `make release-minor`, and `make release-major` automatically stage the current repo changes
- `make publish-current` skips the version bump and commit, and just tags/releases the current `HEAD` using the version already present in `manifest.json`
- the GitHub release step uses `gh release create --generate-notes`, so the GitHub CLI must be installed and authenticated

### Configuration Troubleshooting

- Unable to authenticate with the provided credentials

  - Ensure the provided credentials can authenticate to Hubspace

- Connection timed out when reaching the server

  - Increase the timeout

# Troubleshooting

Device troubleshooting may require a data dump from Hubspace. This can
be generated within the UI, but will need to be retrieved with something
that can access Home Assistants Filestore.

- Navigate to the Hubspace Devices

  - Settings -> Devices & services -> Integrations -> Hubspace

- Click on devices on the navigation bar underneath the Hubspace logo
- Click on the device named labeled `hubspace-<email_address>`
- Click `Press` on `Generate Debug` underneath Controls
- Open File Editor
- Click the folder icon on the top left
- Navigate to custom_components -> hubspace
- Download the required files:

  - `_dump_hs_devices.json`: Anonymized device dumps consumed by the Hubspace integration

# FAQ

- I have a device in Hubspace that is not added to Home Assistant

  - Check the logs for any warning / errors around hubspace and report the issue.
  - If no warning / error messages exist around Hubspace, the device type is likely
    not supported. Refer to the troubleshooting section to grab anonymized logs and
    open a new issue with the logs and state the device that did not discover

- I have a device and its missing functionality

  - Refer to the troubleshooting section to grab anonymized logs and
    open a new issue with the logs and state the device that is not working
    along with the broken functionality

- I have a device and its functionality is not working

  - Refer to the troubleshooting section to grab anonymized logs and
    open a new issue with the logs and state the device that is not working
    along with the broken functionality
  - If the developers are unable to solve the problem with the anonymized data,
    the raw data may need to be provided

- I have a device that does not display the correct model

  - Generate the debug logs and create an issue on GitHub.

- I enabled MFA within my app but I was not forced to re-login.

  - Tokens are not invalidated when you enable MFA and must invalidate them manually. For Hubspace,
    this is done by going to "Manage Account" and clicking "Where You're Signed In", then clicking
    "SIGN OUT OF ALL OTHER DEVICES". Once signed out, the existing token could be valid for up to
    two more minutes. Once the current token is expired, Home Assistant will show there is a repair
    available for "Authentication expired for <email>".

- I adjusted Home Assistants Unit system and now the values are displaying incorrectly

  - After updating the Unit system, you must also reload the integration for the values to show correctly. This
    can be accomplished by going to Settings -> Devices & services -> Hubspace -> Triple dots -> Reload.

_Thanks to everyone who starred this repo. To star it click on the image below, then use the button at the top right._

[![Star History Chart](https://api.star-history.com/svg?repos=SenexCrenshaw/Hubspace-Homeassistant&type=Date)](https://star-history.com/#SenexCrenshaw/Hubspace-Homeassistant&Date)
