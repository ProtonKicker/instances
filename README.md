# Instances

Instances is a Python-based Linux app for running and managing multiple Klipper setups from one place.

For the original rough notes and early roadmap thinking, see [`THOUGHT_PROCESS.md`](file:///home/tovi/Documents/GitHub/instances/THOUGHT_PROCESS.md).

The project bundles the core pieces around a printer stack:

- `klipper`
- `moonraker`
- `mainsail`

and wraps them in a terminal-first manager for creating, organizing, and launching multiple local printer instances.

Right now, the project is in its first major stage: a Klipper instance manager. The longer-term vision is bigger than that, but the current app already works as a practical multi-instance launcher and organizer.

## What It Does

Today, Instances can:

- create printer instances
- assign each instance a label such as `a1`, `a2`, `b1`
- scan serial devices from `/dev/serial/by-id`
- assign USB devices to printers
- copy a Klipper config template into a new instance
- generate per-instance Moonraker and Mainsail setup
- launch and stop Klipper, Moonraker, and a local Mainsail server
- manage one printer or many printers at once
- show a dashboard with instance status and detected USB devices

This makes it useful for testing, small printer farms, or just keeping multiple printer environments organized on one machine.

## Current Direction

The rough roadmap looks like this:

### Stage 1

A Klipper instance manager.

That part is what this repo is focused on now: batch operations, per-printer setup, data directories, labels, board assignment, and local process management.

### Stage 2

A stronger CLI front end around the printer workflow.

The idea here is to move beyond "just launch Mainsail" and make the terminal experience itself feel like the main control surface.

### Stage 3

AI-assisted print farm management.

The long-term vision is a digital manager that helps coordinate very large groups of printers, handle availability, and reduce the manual overhead of farm operations.

## How It Works

The app keeps instance data in a user data directory, creates a folder for each printer, and boots each one with its own:

- `printer.cfg`
- `moonraker.conf`
- `moonraker_data/`
- `mainsail/`

When an instance is started, the app launches:

1. Klipper
2. Moonraker
3. a local static Mainsail server

Each printer gets its own local ports, so multiple instances can run side by side.

## Repo Layout

- `main.py` - interactive terminal app
- `farm.py` - instance storage, setup, ports, and bootstrapping
- `process.py` - process launching and stopping
- `detect.py` - serial device scanning
- `klipper_core/` - bundled Klipper source
- `moonraker_core/` - bundled Moonraker source
- `mainsail_web/` - bundled Mainsail web files

There is also an AppImage in the repo:

- `Farm-x86_64.AppImage`

## Quick Start

Run the app from the project root:

```bash
python3 main.py
```

You can also choose a custom data directory:

```bash
python3 main.py --data-dir /path/to/instances
```

By default, the app uses:

```text
~/Documents/instances
```

and stores its saved config under:

```text
~/.config/farm/config.json
```

## Main Commands

Inside the app, the main flow is built around short commands:

- `p` - add printer
- `d` - dashboard
- `s` - set data directory
- `h` - help
- `sa` - start all printers
- `ka` - stop all printers
- `s-a1` - start one printer
- `k-a1` - stop one printer
- `n-a1` - rename printer
- `l-a1` - relabel printer
- `b-a1` - assign board
- `x-a1` - remove printer

The app also supports grouped selection patterns such as:

- `s-a1:a3`
- `s-a1:b2`
- `k-a1&a3`

You can also type a printer label or name directly to inspect it.

## Notes

- The app expects Linux-style serial device paths.
- Serial devices are scanned from `/dev/serial/by-id`.
- Mainsail is served locally through Python's built-in `http.server`.
- This project is still evolving, so the structure and workflow may continue to change.

## Upstream Versions

Mainsail:

- v2.18.0
- https://github.com/mainsail-crew/mainsail/releases/tag/v2.18.0

Klipper:

- v0.13.0
- https://github.com/Klipper3d/klipper/releases/tag/v0.13.0

## Why This Project Exists

The goal is to make Klipper environments feel easier to package, launch, and manage as a real Linux app instead of a pile of manually connected parts.

For now, that means building a solid multi-instance manager first. Once that foundation is strong, the project can grow into a much more capable command front end and eventually into something useful for large-scale printer operations.
