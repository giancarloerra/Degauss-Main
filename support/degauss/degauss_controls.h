// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DEGAUSS_CONTROLS_H
#define DEGAUSS_CONTROLS_H

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace degauss_controls {

constexpr unsigned ROLE_COUNT = 10;
constexpr unsigned MAX_DEVICES = 30;
constexpr uint32_t INHERIT = UINT32_MAX;
enum Role { UP, DOWN, LEFT, RIGHT, SELECT, BACK, ACTIONS, MENU, PAGE_PREVIOUS, PAGE_NEXT };
using Bindings = std::array<uint16_t, ROLE_COUNT>;

inline void word(std::vector<uint8_t> &out, uint16_t value)
{
	out.push_back(value & 255);
	out.push_back(value >> 8);
}

inline void text(std::vector<uint8_t> &out, const std::string &value)
{
	word(out, static_cast<uint16_t>(value.size()));
	out.insert(out.end(), value.begin(), value.end());
}

inline std::vector<uint8_t> reply(const char *magic)
{
	std::vector<uint8_t> out(magic, magic + 4);
	word(out, 1);
	return out;
}

struct Reader {
	const std::vector<uint8_t> &data;
	size_t at = 0;
	bool u16(uint16_t &value) {
		if (at + 2 > data.size()) return false;
		value = data[at] | (static_cast<uint16_t>(data[at + 1]) << 8);
		at += 2;
		return true;
	}
	bool u32(uint32_t &value) {
		uint16_t lo, hi;
		if (!u16(lo) || !u16(hi)) return false;
		value = lo | (static_cast<uint32_t>(hi) << 16);
		return true;
	}
	bool text(std::string &value) {
		uint16_t length;
		if (!u16(length) || !length || length > 255 || at + length > data.size()) return false;
		value.assign(reinterpret_cast<const char *>(data.data() + at), length);
		at += length;
		return value.find('\0') == std::string::npos;
	}
};

struct Profile {
	std::string id;
	std::array<uint32_t, ROLE_COUNT> bindings;
	Bindings resolve(const Bindings &native) const {
		Bindings result = native;
		for (unsigned i = 0; i < ROLE_COUNT; ++i)
			if (bindings[i] != INHERIT) result[i] = static_cast<uint16_t>(bindings[i]);
		return result;
	}
};

inline bool validate(const Bindings &bindings, std::string &error)
{
	for (unsigned i = 0; i < ROLE_COUNT; ++i) {
		if (!bindings[i] && i <= BACK) {
			error = "A required direction, Select or Back is unassigned";
			return false;
		}
		if (bindings[i]) for (unsigned j = 0; j < i; ++j) if (bindings[i] == bindings[j]) {
			error = "Two Degauss controls use the same button or axis direction";
			return false;
		}
	}
	return true;
}

class Store {
	std::vector<Profile> profiles;
public:
	bool empty() const { return profiles.empty(); }
	const Profile *find(const std::string &id) const {
		for (const auto &profile : profiles) if (profile.id == id) return &profile;
		return nullptr;
	}
	void clear() { profiles.clear(); }
	bool read(const std::vector<uint8_t> &data, std::string &error) {
		if (data.size() < 8 || std::string(data.begin(), data.begin() + 4) != "DGCP") {
			error = "Invalid Degauss controller profile header";
			return false;
		}
		Reader reader{data};
		reader.at = 4;
		uint16_t version, count;
		if (!reader.u16(version) || version != 1 || !reader.u16(count) || count > MAX_DEVICES) {
			error = "Unsupported Degauss controller profile version or count";
			return false;
		}
		std::vector<Profile> candidate;
		for (unsigned i = 0; i < count; ++i) {
			Profile profile;
			if (!reader.text(profile.id)) { error = "Invalid controller profile identity"; return false; }
			for (const auto &previous : candidate) if (profile.id == previous.id) {
				error = "Duplicate controller profile identity"; return false;
			}
			for (unsigned role = 0; role < ROLE_COUNT; ++role) {
				uint32_t &code = profile.bindings[role];
				if (!reader.u32(code) || (code != INHERIT && code > 65535)
					|| (!code && role <= BACK)) {
					error = "Invalid or unassigned required controller binding"; return false;
				}
			}
			candidate.push_back(profile);
		}
		if (reader.at != data.size()) { error = "Trailing controller profile data"; return false; }
		profiles.swap(candidate);
		return true;
	}
};

} // namespace degauss_controls
#endif
