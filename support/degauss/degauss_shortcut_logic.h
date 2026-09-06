// Pure state and file-format logic for the Degauss frontend shortcut.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef DEGAUSS_SHORTCUT_LOGIC_H
#define DEGAUSS_SHORTCUT_LOGIC_H

#include <stddef.h>
#include <stdint.h>

namespace degauss_shortcut_logic
{

// Version 1 briefly exposed a controller shortcut before release. Keep its
// byte range readable so test cards do not need their configuration deleted,
// but every keyboard-only save writes the field back to zero.
constexpr uint8_t LEGACY_CONTROLLER_OFF = 0;
constexpr uint8_t LEGACY_CONTROLLER_COUNT = 9;

enum ConfigLoadResult : uint8_t
{
	CONFIG_MISSING,
	CONFIG_VALID,
	CONFIG_INVALID
};

// Stored separately from MiSTer.ini so a stock Main build ignores the feature.
// Fixed-width fields, size, version, and sentinels make truncated, future, and
// corrupt records distinguishable from a deliberately disabled configuration.
struct ConfigV1
{
	uint32_t magic;
	uint16_t version;
	uint16_t size;
	uint16_t keyboard_key;
	uint8_t legacy_controller_button;
	uint8_t reserved;
	uint32_t sentinel;
};

static_assert(sizeof(ConfigV1) == 16, "Degauss shortcut config must remain stable");
static_assert(offsetof(ConfigV1, magic) == 0, "Config magic offset changed");
static_assert(offsetof(ConfigV1, version) == 4, "Config version offset changed");
static_assert(offsetof(ConfigV1, size) == 6, "Config size offset changed");
static_assert(offsetof(ConfigV1, keyboard_key) == 8, "Config key offset changed");
static_assert(offsetof(ConfigV1, legacy_controller_button) == 10,
	"Config legacy controller offset changed");
static_assert(offsetof(ConfigV1, reserved) == 11, "Config reserved offset changed");
static_assert(offsetof(ConfigV1, sentinel) == 12, "Config sentinel offset changed");

constexpr uint32_t CONFIG_MAGIC = 0x43534744; // "DGSC" on little-endian ARM
constexpr uint16_t CONFIG_VERSION = 1;
constexpr uint32_t CONFIG_SENTINEL = 0xA55A5AA5;
// Linux input-event-codes.h defines KEY_MAX as 0x2ff. Keep the pure logic
// header independent of Linux headers so its tests also compile on the host;
// input.cpp asserts this value against the target toolchain's KEY_MAX.
constexpr uint16_t MAX_KEYBOARD_KEY = 0x02ff;
constexpr uint16_t PRIMARY_BUTTON_FIRST = 0x0100;
constexpr uint16_t PRIMARY_BUTTON_LAST = 0x0151;
constexpr uint16_t DPAD_BUTTON_FIRST = 0x0220;
constexpr uint16_t DPAD_BUTTON_LAST = 0x0223;
constexpr uint16_t TRIGGER_BUTTON_FIRST = 0x02c0;
constexpr uint16_t TRIGGER_BUTTON_LAST = 0x02e7;

inline bool valid_keyboard_key(uint16_t key)
{
	if (key > MAX_KEYBOARD_KEY) return false;
	return !(key >= PRIMARY_BUTTON_FIRST && key <= PRIMARY_BUTTON_LAST)
		&& !(key >= DPAD_BUTTON_FIRST && key <= DPAD_BUTTON_LAST)
		&& !(key >= TRIGGER_BUTTON_FIRST && key <= TRIGGER_BUTTON_LAST);
}

inline ConfigV1 make_config(uint16_t keyboard_key)
{
	return {
		CONFIG_MAGIC,
		CONFIG_VERSION,
		static_cast<uint16_t>(sizeof(ConfigV1)),
		keyboard_key,
		LEGACY_CONTROLLER_OFF,
		0,
		CONFIG_SENTINEL
	};
}

inline bool config_valid(const ConfigV1 &config)
{
	return config.magic == CONFIG_MAGIC
		&& config.version == CONFIG_VERSION
		&& config.size == sizeof(ConfigV1)
		&& valid_keyboard_key(config.keyboard_key)
		&& config.legacy_controller_button < LEGACY_CONTROLLER_COUNT
		&& config.reserved == 0
		&& config.sentinel == CONFIG_SENTINEL;
}

inline ConfigLoadResult classify_config(bool file_exists, uint32_t file_size,
	const ConfigV1 *record)
{
	if (!file_exists) return CONFIG_MISSING;
	if (file_size != sizeof(ConfigV1) || !record || !config_valid(*record))
	{
		return CONFIG_INVALID;
	}
	return CONFIG_VALID;
}

struct RuntimeConditions
{
	bool frontend_available;
	bool menu_core;
	bool osd_unlocked;
	bool framebuffer_script;
	bool osd_visible;
};

inline bool runtime_eligible(const RuntimeConditions &conditions,
	bool require_hidden_osd)
{
	return conditions.frontend_available
		&& !conditions.menu_core
		&& conditions.osd_unlocked
		&& !conditions.framebuffer_script
		&& (!require_hidden_osd || !conditions.osd_visible);
}

struct RequestState
{
	bool pending = false;

	void request()
	{
		pending = true;
	}

	bool take(bool eligible)
	{
		const bool result = pending && eligible;
		pending = false;
		return result;
	}
};

struct KeyboardRuntimeState
{
	uint16_t consumed_key = 0;

	bool event(uint16_t configured_key, uint16_t key, int value,
		bool eligible, bool &triggered)
	{
		triggered = false;

		if (consumed_key && key == consumed_key)
		{
			if (!value) consumed_key = 0;
			return true;
		}

		if (!configured_key || key != configured_key || value != 1 || !eligible)
		{
			return false;
		}

		consumed_key = key;
		triggered = true;
		return true;
	}
};

} // namespace degauss_shortcut_logic

#endif
