#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../support/degauss/degauss_shortcut_logic.h"

using namespace degauss_shortcut_logic;

static void test_config_validation()
{
	ConfigV1 config = make_config(87, CONTROLLER_X);
	assert(config_valid(config));

	config.magic = 0;
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_X);
	config.version++;
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_X);
	config.size--;
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_X);
	config.keyboard_key = MAX_KEYBOARD_KEY + 1;
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_COUNT);
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_X);
	config.reserved = 1;
	assert(!config_valid(config));
	config = make_config(87, CONTROLLER_X);
	config.sentinel = 0;
	assert(!config_valid(config));

	config = make_config(87, CONTROLLER_X);
	ConfigV1 reloaded = {};
	memcpy(&reloaded, &config, sizeof(config));
	assert(config_valid(reloaded));
	assert(!memcmp(&config, &reloaded, sizeof(config)));
	const uint8_t expected_bytes[] = {
		0x44, 0x47, 0x53, 0x43,
		0x01, 0x00,
		0x10, 0x00,
		0x57, 0x00,
		CONTROLLER_X, 0x00,
		0xA5, 0x5A, 0x5A, 0xA5
	};
	assert(sizeof(expected_bytes) == sizeof(config));
	assert(!memcmp(&config, expected_bytes, sizeof(config)));

	const ConfigV1 cleared = make_config(0, CONTROLLER_OFF);
	assert(config_valid(cleared));
	assert(cleared.keyboard_key == 0);
	assert(cleared.controller_button == CONTROLLER_OFF);

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

static void test_logical_controller_mapping()
{
	const uint32_t mappings[] = {
		0x130, 0x131, 0x133, 0x134, 0x136, 0x137, 0x13A, 0x13B
	};
	const uint8_t expected[] = {
		CONTROLLER_A, CONTROLLER_B, CONTROLLER_X, CONTROLLER_Y,
		CONTROLLER_L, CONTROLLER_R, CONTROLLER_SELECT, CONTROLLER_START
	};
	for (uint8_t i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
	{
		assert(controller_button_for_code(mappings[i], mappings) == expected[i]);
	}
	assert(controller_button_for_code(0x13C, mappings) == CONTROLLER_OFF);

	uint32_t flagged_mappings[sizeof(mappings) / sizeof(mappings[0])] = {};
	for (uint8_t i = 0; i < sizeof(mappings) / sizeof(mappings[0]); i++)
	{
		flagged_mappings[i] = mappings[i] | 0xABCD0000;
		assert(controller_button_for_code(mappings[i], flagged_mappings) == expected[i]);
	}
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
}

static void test_controller_runtime()
{
	ControllerRuntimeState state;
	bool triggered = false;

	assert(!state.target_event(0x130, 1, true, true, triggered));
	state.prefix_press(false);
	assert(!state.target_event(0x130, 1, true, true, triggered));
	state.prefix_release();

	state.prefix_press(true);
	assert(!state.target_event(0x131, 1, false, true, triggered));
	assert(!triggered);
	assert(!state.target_event(0x130, 1, true, false, triggered));

	assert(state.target_event(0x130, 1, true, true, triggered));
	assert(triggered);
	assert(state.target_event(0x130, 2, false, false, triggered));
	assert(!triggered);
	assert(state.target_event(0x130, 0, false, false, triggered));
	state.prefix_release();

	state.prefix_press(true);
	assert(!state.target_event(0x130, 0, true, true, triggered));
	state.prefix_release();
	assert(!state.target_event(0x130, 1, true, true, triggered));
}

int main()
{
	test_config_validation();
	test_runtime_conditions_and_request();
	test_logical_controller_mapping();
	test_keyboard_runtime();
	test_controller_runtime();
	return 0;
}
