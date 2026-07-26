# Thought Process

This file keeps the original rough notes and early thinking behind the project.

It is not meant to replace the main [`README.md`](file:///home/tovi/Documents/GitHub/instances/README.md). The main README introduces the project as it exists today. This document is here to preserve the original direction, rough planning, and late-night draft energy that started it.

## Original Starting Point

Use Python to package Klipper into a Linux app.

## Versions

Mainsail:

- v2.18.0
- https://github.com/mainsail-crew/mainsail/releases/tag/v2.18.0

Klipper:

- v0.13.0
- https://github.com/Klipper3d/klipper/releases/tag/v0.13.0

## Early Interface Thoughts

Startup screen:

1. welcome
2. data directory
3. list devices
4. some commands available:
   - `dir`
   - `device`
   - `server`

### `dir`

Default dir = `Documents/instance1`

### `device`

List out devices.

### `launch`

Launch Mainsail server.

## Original Intro Draft

This started as a very rough late-night README draft, but the core idea was already there.

The app would have 2 or 3 stages. At the time of writing those notes, it was in the first stage.

### Stage 1

Klipper instance manager.

Manage Klipper or Kalico instances in batch:

- start
- add
- edit
- organize

### Stage 2

Klipper instance manager plus a CLI front end that could eventually replace the need to live inside Mainsail or Fluid all the time.

The idea was that instead of always sending raw G-code commands directly, such as `G28`, the terminal could support more natural commands like:

- `home`

### Stage 3

AI involvement.

The big-picture idea is a digital manager for print farms, where large groups of printers can be coordinated more naturally.

An example of that vision:

> "AI bot, those machines I'm fixing are unavailable, so don't use them, and use the rest of the printers to print 100k benchies."

## Why Keep This File

Projects usually start with rough notes before they turn into solid structure. This file keeps that original thinking intact:

- the packaging goal
- the startup flow ideas
- the staged roadmap
- the print farm vision behind the app

It is here on purpose, because the original thought process still explains the spirit of the project.
