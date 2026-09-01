// Degauss: hand the menu core to the Degauss frontend.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>
#include <string.h>

#include "degauss_launcher.h"
#include "../../cfg.h"
#include "../../file_io.h"
#include "../../user_io.h"

// Where the frontend is installed. The same path the Scripts menu would
// show, so a card that has Degauss already has this and a card that does
// not is left alone.
#define DEGAUSS_SCRIPT "Scripts/degauss.sh"

bool degauss_is_frontend_script(const char *path)
{
	if (!path) return false;
	const char *slash = strrchr(path, '/');
	const char *name = slash ? slash + 1 : path;
	return !strcmp(name, "degauss.sh");
}

bool degauss_installed(void)
{
	return cfg.fb_terminal && FileExists(DEGAUSS_SCRIPT);
}

bool degauss_should_take_menu(char *path, int size)
{
	// Once per Main process. Main re-executes itself on every core load
	// (fpga_io.cpp, app_restart), so this static is fresh every time the
	// menu core comes back, and stays set if the user quits the frontend
	// to the stock menu. Quitting therefore means quitting, rather than
	// the frontend reappearing on top of itself.
	static bool taken = false;
	if (taken) return false;

	// Only the menu core. A game core must never have its screen taken.
	if (!is_menu()) return false;

	// Without the framebuffer terminal there is no way to give a program
	// the screen at all, and the Scripts menu is equally dead. Leaving the
	// stock menu up is the honest outcome.
	if (!degauss_installed()) return false;

	taken = true;
	snprintf(path, size, "%s", DEGAUSS_SCRIPT);
	return true;
}
