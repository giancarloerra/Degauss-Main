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
- A on **Frontend** loads `menu.rbf`. Main then restarts and uses the same
  handoff path.
- Starting `degauss.sh` from the Scripts menu uses the same framebuffer
  execution path without the console banner or final key prompt.
- Cards without functional Degauss support keep the stock Main behaviour.

## Optional return shortcut

Right on the System menu's **Frontend** row opens its shortcut settings.
Both assignments default to Off.

- **Keyboard** captures one physical Linux key code. A starts capture and X
  clears it.
- **Controller** cycles through Off and Menu plus logical A, B, X, Y, L, R,
  Start or Select.
- Menu or B cancels keyboard capture.
- A malformed or unsupported record is displayed as invalid and can only be
  replaced by explicitly resetting both assignments to Off.

The runtime shortcut is accepted only when all of these conditions hold:

- Degauss and the framebuffer terminal are available.
- A non-menu core is running.
- OSD lock is unlocked.
- No framebuffer script owns VT 2.
- A keyboard trigger occurs while the OSD is hidden.
- A controller trigger starts with MiSTer's existing Menu/OSD prefix while
  the OSD is hidden.

The configured keyboard make, repeat and break events are consumed. A
controller target press and release are consumed only after the Menu prefix.
The same controller button without that prefix follows the existing core
path. The Menu prefix keeps its existing Main behaviour.

Input processing records one request. `HandleUI` consumes it and loads
`menu.rbf`; the input path never starts Degauss or loads a core directly.

## Configuration format

The settings are stored at:

```text
/media/fat/config/degauss/frontend_shortcut.bin
```

The version 1 record is a 16-byte little-endian structure containing magic,
version, record size, keyboard key, logical controller choice, a reserved
byte and a sentinel. A missing file means both assignments are Off. Wrong
size, version, field range, reserved value, magic or sentinel is invalid.
Deleting the file restores the missing-file Off default on the next Main
start.

## Local verification

The pure configuration and input-state logic is independent of Main's ARM
dependencies and can be checked on the host:

```bash
./tests/run-degauss-shortcut-tests.sh
```

The complete fork build uses the existing containerised ARM toolchain:

```bash
./build-degauss-main.sh
```
