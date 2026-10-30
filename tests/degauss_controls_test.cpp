#include "../support/degauss/degauss_controls.h"
#include <cassert>

using namespace degauss_controls;

static void dword(std::vector<uint8_t> &out, uint32_t value)
{
	word(out, value & 65535);
	word(out, value >> 16);
}

static std::vector<uint8_t> profile(const std::string &id, const std::array<uint32_t, ROLE_COUNT> &bindings)
{
	auto data = reply("DGCP");
	word(data, 1);
	text(data, id);
	for (auto code : bindings) dword(data, code);
	return data;
}

int main()
{
	const Bindings native{{10, 11, 12, 13, 14, 15, 16, 17, 18, 19}};
	std::array<uint32_t, ROLE_COUNT> bindings;
	bindings.fill(INHERIT);
	Store store;
	std::string error;
	assert(store.empty());
	assert(store.read(profile("controller", bindings), error));
	assert(store.find("controller")->resolve(native) == native);
	assert(!store.find("different controller"));
	bindings[SELECT] = 300;
	bindings[ACTIONS] = 0;
	assert(store.read(profile("controller", bindings), error));
	auto effective = store.find("controller")->resolve(native);
	assert(effective[SELECT] == 300 && effective[BACK] == native[BACK] && !effective[ACTIONS]);
	assert(validate(effective, error));
	effective[BACK] = 300;
	assert(!validate(effective, error));
	effective = native;
	effective[UP] = 0;
	assert(!validate(effective, error));
	bindings[BACK] = 0;
	assert(!store.read(profile("controller", bindings), error));
	assert(store.find("controller")->resolve(native)[BACK] == native[BACK]);
	bindings[BACK] = 65536;
	assert(!store.read(profile("controller", bindings), error));
	bindings[BACK] = INHERIT;
	auto valid = profile("controller", bindings);
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
	assert(store.find("controller")->resolve(native)[SELECT] == 300);
	auto reset = reply("DGCP");
	word(reset, 0);
	assert(store.read(reset, error) && store.empty());
}
