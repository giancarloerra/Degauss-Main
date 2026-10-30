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
constexpr unsigned DIRECTION_BINDINGS = 3;
constexpr unsigned MAX_DEVICES = 30;
enum Role { UP, DOWN, LEFT, RIGHT, SELECT, BACK, ACTIONS, MENU, PAGE_PREVIOUS, PAGE_NEXT };
using Bindings = std::array<uint16_t, ROLE_COUNT>;
struct Binding { uint16_t code; std::string label; };
using Controls = std::array<std::vector<Binding>, ROLE_COUNT>;

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
	word(out, 3);
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
	bool text(std::string &value, size_t maximum = 255) {
		uint16_t length;
		if (!u16(length) || !length || length > maximum || at + length > data.size()) return false;
		value.assign(reinterpret_cast<const char *>(data.data() + at), length);
		at += length;
		return value.find('\0') == std::string::npos;
	}
};

struct Profile {
	std::string id;
	Controls bindings;
	Bindings primary() const {
		Bindings result{};
		for (unsigned i = 0; i < ROLE_COUNT; ++i) if (!bindings[i].empty()) result[i] = bindings[i][0].code;
		return result;
	}
	std::string label(unsigned role) const { return bindings[role].empty() ? "Unassigned" : bindings[role][0].label; }
	bool contains(uint16_t code) const {
		for (const auto &role : bindings) for (const auto &binding : role) if (binding.code == code) return true;
		return false;
	}
};

inline bool validate(const Controls &bindings, std::string &error)
{
	for (unsigned i = 0; i < ROLE_COUNT; ++i) {
		if (bindings[i].empty() && i <= BACK) {
			error = "A required direction, Select or Back is unassigned";
			return false;
		}
		if (bindings[i].size() > (i < SELECT ? DIRECTION_BINDINGS : 1U)) {
			error = "Too many bindings for a Degauss control"; return false;
		}
		for (unsigned at = 0; at < bindings[i].size(); ++at) {
			const auto &binding = bindings[i][at];
			if (!binding.code || binding.label.empty() || binding.label.size() > 48 || binding.label.find('\0') != std::string::npos) {
				error = "Invalid controller binding or label"; return false;
			}
			for (unsigned j = 0; j <= i; ++j) for (unsigned n = 0; n < bindings[j].size(); ++n) {
				if (j == i && n >= at) break;
				if (binding.code == bindings[j][n].code) {
					error = "Two Degauss controls use the same button or axis direction"; return false;
				}
			}
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
		if (!reader.u16(version) || version != 3 || !reader.u16(count) || count > MAX_DEVICES) {
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
				uint16_t size;
				if (!reader.u16(size) || size > (role < SELECT ? DIRECTION_BINDINGS : 1U)) {
					error = "Invalid controller binding count"; return false;
				}
				for (unsigned n = 0; n < size; ++n) {
					Binding binding{};
					if (!reader.u16(binding.code) || !reader.text(binding.label, 48)) {
						error = "Invalid controller binding data"; return false;
					}
					profile.bindings[role].push_back(binding);
				}
			}
			if (!validate(profile.bindings, error)) return false;
			candidate.push_back(profile);
		}
		if (reader.at != data.size()) { error = "Trailing controller profile data"; return false; }
		profiles.swap(candidate);
		return true;
	}
};

} // namespace degauss_controls
#endif
