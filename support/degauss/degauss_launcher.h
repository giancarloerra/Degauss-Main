// Degauss: hand the menu core to the Degauss frontend.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later
//
// This file is part of a fork of MiSTer Main and is therefore GPL-3.0, the
// same as Main itself. The Degauss frontend is a separate program under a
// different licence; nothing here links against it. All this does is start
// it the same way the Scripts menu starts any other script.

#ifndef DEGAUSS_LAUNCHER_H
#define DEGAUSS_LAUNCHER_H

// True when the menu core has just come up and the frontend should be given
// the screen. Answers true at most once per Main process, and Main re-execs
// itself on every core load, so that is once per return to the menu.
//
// Writes the script path into `path`, in the form the Scripts menu uses:
// relative to the root directory.
bool degauss_should_take_menu(char *path, int size);

// Which entries of the core's System menu the Degauss items occupy.
//
// menumask bits are menusub values, not line positions, so an item can be
// drawn anywhere and numbered anything free. The number still decides the
// order the stick walks through them. These two are deliberately above every
// upstream entry and consecutive: Frontend walks down to Frontend shortcut,
// then wraps to Core. Up walks through the same visible order in reverse.
#define DEGAUSS_MENUSUB 30
#define DEGAUSS_SHORTCUT_MENUSUB 31

// True when `path` names the frontend's own script.
//
// The frontend draws its own screen and leaves on purpose, so it wants
// neither the console banner on the way in nor the "press any key" on the
// way out that an ordinary shell script needs. Asking about the path
// rather than about how it was started covers both routes to it: the
// automatic handover above, and picking it from the Scripts menu by hand.
bool degauss_is_frontend_script(const char *path);

// True when the frontend script and framebuffer terminal are available, so
// the Frontend entry can work. Other cards get the stock menu untouched.
bool degauss_installed(void);

#endif
