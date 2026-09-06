// Degauss frontend shortcut integration for MiSTer Main.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef DEGAUSS_SHORTCUT_H
#define DEGAUSS_SHORTCUT_H

#include <stdint.h>

#include "degauss_shortcut_logic.h"

enum DegaussShortcutLoadState
{
	DEGAUSS_SHORTCUT_MISSING,
	DEGAUSS_SHORTCUT_VALID,
	DEGAUSS_SHORTCUT_INVALID
};

// Configuration access. A missing file is the documented Off default.
DegaussShortcutLoadState degauss_shortcut_load_state(void);
uint16_t degauss_shortcut_keyboard_key(void);
bool degauss_shortcut_set_keyboard(uint16_t key);
bool degauss_shortcut_reset(void);

// Keyboard capture is initiated by the OSD and completed by a physical Linux
// keyboard event. Controller-generated menu events are excluded by the caller.
void degauss_shortcut_begin_keyboard_capture(void);
void degauss_shortcut_cancel_keyboard_capture(void);
bool degauss_shortcut_take_keyboard_capture(uint16_t *key);

// The input hook returns true when the current event must not reach the core.
bool degauss_shortcut_handle_keyboard_event(uint16_t key, int value, bool menu_event);

// The input path only records a request. HandleUI performs the core load.
bool degauss_shortcut_take_request(void);

#endif
