# Degauss integration in MiSTer Main

This directory contains the Degauss-specific integration maintained by the
Degauss fork of MiSTer Main. A stock Main build ignores Degauss and does not
read its shortcut configuration.

## Existing frontend handoff

`degauss_launcher.cpp` retains the existing paths:

- A menu-core start hands the framebuffer terminal to
  `Scripts/degauss.sh` once per Main process.
- The System menu contains **Frontend** when `fb_terminal=1` and that script
  exists.
- Selecting **Frontend** loads `menu.rbf`. Main then restarts and uses the same
  handoff path.
- Starting `degauss.sh` from the Scripts menu uses the same framebuffer
  execution path without the console banner or final key prompt.
- Cards without functional Degauss support keep the stock Main behaviour.
- Exiting the frontend opens the native core chooser at the root when the
  private Degauss Menu core is active. Ordinary core and MRA locations are unchanged.

## Frontend controller controls

While the Degauss frontend is active, it can inspect connected controllers,
capture Main-processed button and axis-direction codes, and apply optional
frontend-only profiles through `degauss_controller` commands. Responses are
versioned status records in `/tmp`; the frontend owns persistence in its
`settings.toml`. Main's native menu and game mappings are never overwritten.
Profiles stop applying when the native OSD, a script or a game owns input.
The active-controller report lets the frontend display the effective bindings
and avoid reading keyboard-style controller events a second time.

## Optional return shortcut

The System menu's **Frontend shortcut** row, directly below **Frontend**, opens
the shortcut settings with A. Keyboard and Controller both default to Off.

- **Keyboard** captures one physical Linux key code. A starts capture and X
  clears it.
- **Controller** captures one physical Linux button code. Hold it continuously
  for five seconds to return once; release before another hold. Ordinary button
  events still reach the running core immediately. Disconnecting, changing core
  or opening the OSD clears the hold.
- Menu or B cancels keyboard capture.
- A malformed or unsupported record is displayed as invalid and can only be
  replaced by explicitly resetting the shortcut to Off.

The runtime shortcut is accepted only when all of these conditions hold:

- Degauss and the framebuffer terminal are available.
- A non-menu core is running.
- OSD lock is unlocked.
- No framebuffer script owns VT 2.
- The trigger occurs while the OSD is hidden.

The configured keyboard make, repeat and break events are consumed.

Input processing records one request. `HandleUI` consumes it and loads
`menu.rbf`; the input path never starts Degauss or loads a core directly.

## Configuration format

The settings are stored at:

```text
/media/fat/config/degauss/frontend_shortcut.bin
```

Existing 16-byte version 1 records remain readable with their keyboard key and
Controller Off. The retired controller byte does not enable a hold shortcut.
New saves use a 20-byte version 2 record containing the keyboard key and physical
controller code, preserving each assignment independently. A missing file means
both are Off. Wrong size, version, field range, reserved value, magic or sentinel
is invalid. Deleting the file restores the missing-file Off defaults on the next
Main start.

## Script display handover

The owning Main marks its frontend child with `DEGAUSS_NATIVE_SCRIPTS=1`.
For a selected script, the frontend saves its existing script-resume record and
exact return command, releases its resources and exits with status 42. Main
finishes the normal frontend cleanup, then starts the selected script through
the native `MENU_SCRIPTS_FB` and agetty/tty2 path used by OSD Scripts. There is
no script-specific display mode. After the native result/key-to-return flow,
Main starts exactly one frontend with its original arguments and selection.
Native script children acquire their own terminal session so Ctrl-C reaches
foreground jobs in both OSD Scripts and Degauss-selected scripts.

`DEGAUSS_SCRIPT_HANDOVER=1` and the acknowledged `fb_degauss` command remain
for initial framebuffer readiness and compatibility with older frontends.
Stock-Main on-demand launches preserve their existing execution path.

Only a cold-boot Menu handover sets `DEGAUSS_BOOT_START=1`; game, script and
Frontend-shortcut returns clear it. The frontend owns the optional last-game
setting and its once-per-Linux-boot attempt.

## Local verification

Native analog framebuffer output uses its measured colour-clock calculation,
not ordinary Menu's clock-specific `yc.txt` overrides. Ordinary Menu and game
core overrides, shared-scaler output and Direct Video keep their existing paths.
Native-state transitions resend Y/C parameters without waiting for video-info
metadata to change. RGB/component and unchanged-state transitions add no writes.

The pure configuration and input-state logic is independent of Main's ARM
dependencies and can be checked on the host:

```bash
./tests/run-degauss-shortcut-tests.sh
python3 tests/run-degauss-yc-tests.py
python3 tests/run-degauss-core-menu-tests.py
python3 tests/degauss_script_handover_test.py
python3 tests/degauss_native_scripts_test.py
```

The complete fork build uses the existing containerised ARM toolchain:

```bash
./build-degauss-main.sh
```
