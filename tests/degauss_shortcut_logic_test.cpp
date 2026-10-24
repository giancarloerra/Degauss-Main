#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../support/degauss/degauss_shortcut_logic.h"

using namespace degauss_shortcut_logic;

static void test_config_validation()
{
	const uint16_t braille_dot_1 = 0x01f1;
	assert(MAX_KEYBOARD_KEY == 0x02ff);
	assert(config_valid(make_config(braille_dot_1)));
	assert(config_valid(make_config(0x02bb)));
	assert(!config_valid(make_config(PRIMARY_BUTTON_FIRST)));
	assert(!config_valid(make_config(PRIMARY_BUTTON_LAST)));
	assert(!config_valid(make_config(DPAD_BUTTON_FIRST)));
	assert(!config_valid(make_config(DPAD_BUTTON_LAST)));
	assert(!config_valid(make_config(TRIGGER_BUTTON_FIRST)));
	assert(!config_valid(make_config(TRIGGER_BUTTON_LAST)));

	ConfigV1 config = make_config(87);
	assert(config_valid(config));

	config.magic = 0;
	assert(!config_valid(config));
	config = make_config(87);
	config.version++;
	assert(!config_valid(config));
	config = make_config(87);
	config.size--;
	assert(!config_valid(config));
	config = make_config(87);
	config.keyboard_key = MAX_KEYBOARD_KEY + 1;
	assert(!config_valid(config));
	config = make_config(87);
	config.legacy_controller_button = LEGACY_CONTROLLER_COUNT;
	assert(!config_valid(config));
	config = make_config(87);
	config.reserved = 1;
	assert(!config_valid(config));
	config = make_config(87);
	config.sentinel = 0;
	assert(!config_valid(config));

	config = make_config(87);
	ConfigV1 reloaded = {};
	memcpy(&reloaded, &config, sizeof(config));
	assert(config_valid(reloaded));
	assert(!memcmp(&config, &reloaded, sizeof(config)));
	const uint8_t expected_bytes[] = {
		0x44, 0x47, 0x53, 0x43,
		0x01, 0x00,
		0x10, 0x00,
		0x57, 0x00,
		LEGACY_CONTROLLER_OFF, 0x00,
		0xA5, 0x5A, 0x5A, 0xA5
	};
	assert(sizeof(expected_bytes) == sizeof(config));
	assert(!memcmp(&config, expected_bytes, sizeof(config)));

	const ConfigV1 cleared = make_config(0);
	assert(config_valid(cleared));
	assert(cleared.keyboard_key == 0);
	assert(cleared.legacy_controller_button == LEGACY_CONTROLLER_OFF);

	// A file written by the unreleased controller-capable build remains valid,
	// but every new keyboard-only save clears its legacy controller byte.
	ConfigV1 legacy = make_config(87);
	legacy.legacy_controller_button = LEGACY_CONTROLLER_COUNT - 1;
	assert(config_valid(legacy));
	const ConfigV1 next_save = make_config(legacy.keyboard_key);
	assert(next_save.keyboard_key == legacy.keyboard_key);
	assert(next_save.legacy_controller_button == LEGACY_CONTROLLER_OFF);

	assert(classify_config(false, 0, nullptr) == CONFIG_MISSING);
	assert(classify_config(true, 0, nullptr) == CONFIG_INVALID);
	assert(classify_config(true, sizeof(config) - 1, &config) == CONFIG_INVALID);
	assert(classify_config(true, sizeof(config), nullptr) == CONFIG_INVALID);
	assert(classify_config(true, sizeof(config), &config) == CONFIG_VALID);
}

static void test_runtime_conditions_and_request()
{
	RuntimeConditions conditions = { true, false, true, false, false };
	assert(runtime_eligible(conditions, true));

	conditions.frontend_available = false;
	assert(!runtime_eligible(conditions, false));
	conditions = { true, true, true, false, false };
	assert(!runtime_eligible(conditions, false));
	conditions = { true, false, false, false, false };
	assert(!runtime_eligible(conditions, false));
	conditions = { true, false, true, true, false };
	assert(!runtime_eligible(conditions, false));
	conditions = { true, false, true, false, true };
	assert(runtime_eligible(conditions, false));
	assert(!runtime_eligible(conditions, true));

	RequestState request;
	assert(!request.take(true));
	request.request();
	request.request();
	assert(request.take(true));
	assert(!request.take(true));
	request.request();
	assert(!request.take(false));
	assert(!request.take(true));
}

static void test_keyboard_runtime()
{
	KeyboardRuntimeState state;
	bool triggered = false;

	assert(!state.event(0, 87, 1, true, triggered));
	assert(!triggered);
	assert(!state.event(87, 86, 1, true, triggered));
	assert(!state.event(87, 87, 1, false, triggered));

	assert(state.event(87, 87, 1, true, triggered));
	assert(triggered);
	assert(state.event(87, 87, 2, false, triggered));
	assert(!triggered);
	assert(state.event(87, 87, 0, false, triggered));
	assert(!state.event(87, 87, 0, true, triggered));

	// Linux keyboard codes above MiSTer's legacy 256-entry keyboard map remain
	// valid shortcut keys and retain the same make, repeat and break behavior.
	const uint16_t braille_dot_1 = 0x01f1;
	KeyboardRuntimeState high_key_state;
	assert(high_key_state.event(braille_dot_1, braille_dot_1, 1, true, triggered));
	assert(triggered);
	assert(high_key_state.event(braille_dot_1, braille_dot_1, 2, false, triggered));
	assert(!triggered);
	assert(high_key_state.event(braille_dot_1, braille_dot_1, 0, false, triggered));
}

static void test_hold_config()
{
	const ConfigV2 config = make_hold_config(87, 0x130);
	assert(config_valid(config));
	assert(config.keyboard_key == 87);
	assert(config.controller_button == 0x130);
	ConfigV2 invalid = config;
	invalid.controller_button = 87;
	assert(!config_valid(invalid));
	invalid = config;
	invalid.reserved = 1;
	assert(!config_valid(invalid));
	assert(config_valid(make_hold_config(0, 0)));
	// A legacy controller assignment must stay disabled after migration.
	ConfigV1 legacy = make_config(87);
	legacy.legacy_controller_button = 8;
	assert(config_valid(legacy));
	const ConfigV2 migrated = make_hold_config(legacy.keyboard_key, 0);
	assert(migrated.keyboard_key == legacy.keyboard_key);
	assert(!migrated.controller_button);
}

static void test_controller_hold()
{
	ControllerHoldState first, second;
	first.event(1, true, 100);
	assert(!first.poll(true, 5099));
	first.event(2, true, 2000); // Autorepeat must not restart or trigger a hold.
	assert(first.poll(true, 5100));
	assert(!first.poll(true, 12000));
	first.event(0, true, 12001);
	assert(!first.poll(true, 20000));
	first.event(1, true, 20001);
	first.event(0, true, 24999);
	assert(!first.poll(true, 25001));
	first.event(1, true, 30000);
	assert(!first.poll(false, 34000)); // OSD, disconnect, or lost eligibility resets.
	assert(!first.poll(true, 36000));
	first.event(1, false, 40000);
	assert(!first.poll(true, 50000));
	first.event(1, true, UINT32_MAX - 100);
	assert(!first.poll(true, 4898));
	assert(first.poll(true, 4899)); // Monotonic counter rollover.
	first.reset();
	first.event(1, true, 0);
	second.event(1, true, 4000);
	first.event(0, true, 4500);
	assert(!first.poll(true, 5000));
	assert(!second.poll(true, 5000));
	assert(second.poll(true, 9000)); // Different devices never combine hold time.
}

int main()
{
	test_config_validation();
	test_runtime_conditions_and_request();
	test_keyboard_runtime();
	test_hold_config();
	test_controller_hold();
	return 0;
}
