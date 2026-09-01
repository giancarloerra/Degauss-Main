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

// Configuration access. A missing file is the documented default: both Off.
DegaussShortcutLoadState degauss_shortcut_load_state(void);
uint16_t degauss_shortcut_keyboard_key(void);
uint8_t degauss_shortcut_controller_button(void);
const char *degauss_shortcut_controller_name(uint8_t button);
bool degauss_shortcut_set_keyboard(uint16_t key);
bool degauss_shortcut_set_controller(uint8_t button);
bool degauss_shortcut_reset(void);

// Keyboard capture is initiated by the OSD and completed by a physical Linux
// keyboard event. Controller-generated menu events are excluded by the caller.
void degauss_shortcut_begin_keyboard_capture(void);
void degauss_shortcut_cancel_keyboard_capture(void);
bool degauss_shortcut_take_keyboard_capture(uint16_t *key);

// Input hooks return true when the current event must not reach the core.
bool degauss_shortcut_handle_keyboard_event(uint16_t key, int value, bool menu_event);
bool degauss_shortcut_handle_controller_event(
	degauss_shortcut_logic::ControllerRuntimeState &state,
	uint16_t code, int value,
	bool prefix_pressed, bool prefix_released, bool prefix_was_hidden,
	uint8_t logical_button);

// The input path only records a request. HandleUI performs the core load.
bool degauss_shortcut_take_request(void);

#endif
