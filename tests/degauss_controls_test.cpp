#include "../support/degauss/degauss_controls.h"
#include <cassert>

using namespace degauss_controls;

static std::vector<uint8_t> profile(const std::string &id, const Controls &bindings)
{
	auto data = reply("DGCP");
	word(data, 1);
	text(data, id);
	for (const auto &role : bindings) {
		word(data, role.size());
		for (const auto &binding : role) { word(data, binding.code); text(data, binding.label); }
	}
	return data;
}

int main()
{
	const Bindings native{{10, 11, 12, 13, 14, 15, 16, 17, 18, 19}};
	Controls bindings;
	for (unsigned role = 0; role < ROLE_COUNT; ++role) bindings[role].push_back({native[role], "Native"});
	bindings[LEFT].push_back({1000, "Stick Left"});
	Store store;
	std::string error;
	assert(store.empty());
	assert(store.read(profile("controller", bindings), error));
	assert(store.find("controller")->primary() == native);
	assert(store.find("controller")->contains(1000));
	assert(!store.find("different controller"));
	bindings[SELECT] = {{300, "L"}};
	bindings[ACTIONS].clear();
	assert(store.read(profile("controller", bindings), error));
	auto effective = store.find("controller")->primary();
	assert(effective[SELECT] == 300 && effective[BACK] == native[BACK] && !effective[ACTIONS]);
	assert(store.find("controller")->label(SELECT) == "L");
	assert(validate(bindings, error));
	bindings[BACK] = {{300, "R"}};
	assert(!store.read(profile("controller", bindings), error));
	assert(store.find("controller")->primary()[BACK] == native[BACK]);
	bindings[BACK] = {{0, "Back"}};
	assert(!store.read(profile("controller", bindings), error));
	bindings[BACK] = {{native[BACK], std::string(49, 'B')}};
	assert(!store.read(profile("controller", bindings), error));
	bindings[BACK] = {{native[BACK], "Back"}};
	const auto up = bindings[UP];
	bindings[UP].clear();
	assert(!store.read(profile("controller", bindings), error));
	bindings[UP] = up;
	auto valid = profile("controller", bindings);
	auto legacy = valid; legacy[4] = 1;
	assert(!store.read(legacy, error)); // never interpret an old partial profile as a complete map
	for (size_t length = 0; length < valid.size(); ++length) {
		assert(!store.read(std::vector<uint8_t>(valid.begin(), valid.begin() + length), error));
	}
	auto extra = valid;
	extra.push_back(0);
	assert(!store.read(extra, error));
	auto duplicate = valid;
	duplicate[6] = 2;
	duplicate.insert(duplicate.end(), valid.begin() + 8, valid.end());
	assert(!store.read(duplicate, error));
	assert(store.find("controller")->primary()[SELECT] == 300);
	auto reset = reply("DGCP");
	word(reset, 0);
	assert(store.read(reset, error) && store.empty());
}
