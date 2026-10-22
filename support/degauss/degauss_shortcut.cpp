// Degauss frontend shortcut integration for MiSTer Main.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>
#include <string.h>

#include "degauss_shortcut.h"
#include "degauss_launcher.h"
#include "../../file_io.h"
#include "../../menu.h"
#include "../../user_io.h"
#include "../../video.h"
#include "../../hardware.h"

namespace
{

constexpr const char *CONFIG_NAME = "degauss/frontend_shortcut.bin";
constexpr const char *CONFIG_PATH = CONFIG_DIR "/degauss/frontend_shortcut.bin";

using degauss_shortcut_logic::ConfigV1;
using degauss_shortcut_logic::ConfigV2;
using degauss_shortcut_logic::KeyboardRuntimeState;
using degauss_shortcut_logic::RequestState;

ConfigV2 config = degauss_shortcut_logic::make_hold_config(0, 0);
DegaussShortcutLoadState load_state = DEGAUSS_SHORTCUT_MISSING;
bool loaded = false;
RequestState request_state;

bool capture_active = false;
bool capture_ready = false;
uint16_t capture_key = 0;
uint16_t capture_release_key = 0;

KeyboardRuntimeState keyboard_state;
degauss_shortcut_logic::ControllerHoldState controller_states[30];
bool controller_capture = false;
bool controller_capture_ready = false;
uint16_t controller_capture_button = 0;
uint16_t controller_capture_release = 0;

void ensure_loaded()
{
	if (loaded) return;
	loaded = true;

	const bool exists = FileExists(CONFIG_PATH);
	const int size = FileLoadConfig(CONFIG_NAME, nullptr, 0);
	ConfigV2 candidate = {};
	bool read = size == static_cast<int>(sizeof(candidate))
		&& FileLoadConfig(CONFIG_NAME, &candidate, sizeof(candidate))
			== static_cast<int>(sizeof(candidate));
	if (!exists) return;
	if (size == static_cast<int>(sizeof(ConfigV1)))
	{
		ConfigV1 legacy = {};
		read = FileLoadConfig(CONFIG_NAME, &legacy, sizeof(legacy)) == static_cast<int>(sizeof(legacy))
			&& degauss_shortcut_logic::config_valid(legacy);
		if (read) candidate = degauss_shortcut_logic::make_hold_config(legacy.keyboard_key, 0);
	}
	if (!read || !degauss_shortcut_logic::config_valid(candidate))
	{
		load_state = DEGAUSS_SHORTCUT_INVALID;
		printf("Degauss shortcut config is invalid or unsupported (size %d): %s\n",
			size, CONFIG_PATH);
		return;
	}

	config = candidate;
	load_state = DEGAUSS_SHORTCUT_VALID;
}

bool save_config(const ConfigV2 &candidate)
{
	if (!degauss_shortcut_logic::config_valid(candidate)) return false;

	ConfigV2 stored = candidate;
	if (FileSaveConfig(CONFIG_NAME, &stored, sizeof(stored))
		!= static_cast<int>(sizeof(stored)))
	{
		printf("Degauss shortcut config save failed: %s\n", CONFIG_PATH);
		return false;
	}

	config = candidate;
	load_state = DEGAUSS_SHORTCUT_VALID;
	loaded = true;
	return true;
}

bool runtime_eligible(bool require_hidden_osd)
{
	const degauss_shortcut_logic::RuntimeConditions conditions = {
		degauss_installed(),
		is_menu() != 0,
		menu_osd_is_unlocked(),
		video_fb_state() && video_chvt(0) == 2,
		user_io_osd_is_visible() != 0
	};
	return degauss_shortcut_logic::runtime_eligible(conditions, require_hidden_osd);
}

} // namespace

DegaussShortcutLoadState degauss_shortcut_load_state(void)
{
	ensure_loaded();
	return load_state;
}

uint16_t degauss_shortcut_keyboard_key(void)
{
	ensure_loaded();
	return load_state == DEGAUSS_SHORTCUT_INVALID ? 0 : config.keyboard_key;
}

bool degauss_shortcut_set_keyboard(uint16_t key)
{
	ensure_loaded();
	if (load_state == DEGAUSS_SHORTCUT_INVALID
		|| !degauss_shortcut_logic::valid_keyboard_key(key))
	{
		return false;
	}

	return save_config(degauss_shortcut_logic::make_hold_config(key, config.controller_button));
}

uint16_t degauss_shortcut_controller_button(void)
{
	ensure_loaded();
	return load_state == DEGAUSS_SHORTCUT_INVALID ? 0 : config.controller_button;
}

bool degauss_shortcut_set_controller(uint16_t button)
{
	ensure_loaded();
	if (load_state == DEGAUSS_SHORTCUT_INVALID
		|| !degauss_shortcut_logic::valid_controller_button(button)) return false;
	if (!save_config(degauss_shortcut_logic::make_hold_config(config.keyboard_key, button))) return false;
	degauss_shortcut_reset_controllers();
	return true;
}

bool degauss_shortcut_reset(void)
{
	degauss_shortcut_reset_controllers();
	return save_config(degauss_shortcut_logic::make_hold_config(0, 0));
}

void degauss_shortcut_begin_keyboard_capture(void)
{
	capture_active = true;
	capture_ready = false;
	capture_key = 0;
}

void degauss_shortcut_cancel_keyboard_capture(void)
{
	capture_active = false;
	capture_ready = false;
	capture_key = 0;
	controller_capture = controller_capture_ready = false;
}

void degauss_shortcut_begin_controller_capture(void)
{
	degauss_shortcut_cancel_keyboard_capture();
	controller_capture = true;
	controller_capture_button = 0;
}

bool degauss_shortcut_take_controller_capture(uint16_t *button)
{
	if (!controller_capture_ready) return false;
	if (button) *button = controller_capture_button;
	controller_capture_ready = false;
	return true;
}

bool degauss_shortcut_handle_controller_event(unsigned device, uint16_t button, int value)
{
	if (device >= sizeof(controller_states) / sizeof(controller_states[0])) return false;
	if (controller_capture && button && value == 1)
	{
		controller_capture = false;
		controller_capture_ready = true;
		controller_capture_button = controller_capture_release = button;
		return true;
	}
	if (controller_capture_release == button)
	{
		if (!value) controller_capture_release = 0;
		return true;
	}
	ensure_loaded();
	if (load_state != DEGAUSS_SHORTCUT_INVALID && config.controller_button
		&& button == config.controller_button)
	{
		controller_states[device].event(value, runtime_eligible(true), GetTimer(0));
	}
	return false;
}

void degauss_shortcut_reset_controllers(void)
{
	for (auto &state : controller_states) state.reset();
}

void degauss_shortcut_poll_controllers(void)
{
	bool held = false;
	for (const auto &state : controller_states) held |= state.down;
	if (!held) return;
	const bool eligible = runtime_eligible(true);
	const uint32_t now = GetTimer(0);
	for (auto &state : controller_states)
		if (state.poll(eligible, now)) request_state.request();
}

bool degauss_shortcut_take_keyboard_capture(uint16_t *key)
{
	if (!capture_ready) return false;
	if (key) *key = capture_key;
	capture_ready = false;
	return true;
}

bool degauss_shortcut_handle_keyboard_event(uint16_t key, int value, bool menu_event)
{
	ensure_loaded();

	if (!menu_event && capture_active)
	{
		if (!value) return false;
		if (value == 1 && key)
		{
			capture_active = false;
			capture_ready = true;
			capture_key = key;
			capture_release_key = key;
		}
		return true;
	}

	if (!menu_event && capture_release_key && key == capture_release_key)
	{
		if (!value) capture_release_key = 0;
		return true;
	}

	if (menu_event || load_state == DEGAUSS_SHORTCUT_INVALID) return false;

	const bool needs_eligibility = !keyboard_state.consumed_key
		&& config.keyboard_key
		&& key == config.keyboard_key
		&& value == 1;
	bool triggered = false;
	const bool consumed = keyboard_state.event(config.keyboard_key, key, value,
		needs_eligibility && runtime_eligible(true), triggered);
	if (triggered) request_state.request();
	return consumed;
}

bool degauss_shortcut_take_request(void)
{
	if (!request_state.pending) return false;
	return request_state.take(runtime_eligible(false));
}
