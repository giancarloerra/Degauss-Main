#include "physical_cd_logic.h"

#include <string.h>

static bool contains_bytes(const uint8_t *haystack, size_t haystack_size,
	const char *needle, size_t needle_size)
{
	if (!needle_size || needle_size > haystack_size) return false;
	for (size_t i = 0; i + needle_size <= haystack_size; i++)
	{
		if (!memcmp(haystack + i, needle, needle_size)) return true;
	}
	return false;
}

degauss_cd_disc_type_t degauss_cd_initial_type(bool has_data_track,
	bool has_mdplus)
{
	if (!has_data_track) return DEGAUSS_CD_AUDIO;
	if (has_mdplus) return DEGAUSS_CD_MDPLUS;
	return DEGAUSS_CD_NONE;
}

degauss_cd_disc_type_t degauss_cd_final_type(bool has_snes_rom)
{
	return has_snes_rom ? DEGAUSS_CD_SNES_MSU1 : DEGAUSS_CD_UNKNOWN;
}

degauss_cd_disc_type_t degauss_cd_sector_zero_type(const uint8_t *sector,
	size_t size)
{
	if (size >= 14 && !memcmp(sector, "SEGADISCSYSTEM", 14))
		return DEGAUSS_CD_MEGACD;
	if (size >= 15 && !memcmp(sector, "SEGA SEGASATURN", 15))
		return DEGAUSS_CD_SATURN;
	if (size >= 6 && sector[0] == 0x01 && sector[1] == 0x5A &&
		sector[2] == 0x5A && sector[3] == 0x5A && sector[4] == 0x5A &&
		sector[5] == 0x5A)
		return DEGAUSS_CD_3DO;
	return DEGAUSS_CD_NONE;
}

degauss_cd_disc_type_t degauss_cd_pvd_type(const uint8_t *sector,
	size_t size)
{
	if (size >= 19 && !memcmp(sector + 1, "CD001", 5))
	{
		if (!memcmp(sector + 8, "PLAYSTATION", 11)) return DEGAUSS_CD_PSX;
		if (!memcmp(sector + 8, "NGCD", 4)) return DEGAUSS_CD_NEOGEOCD;
	}
	if (size >= 5 && !memcmp(sector + 1, "CD-I", 4)) return DEGAUSS_CD_CDI;
	return DEGAUSS_CD_NONE;
}

degauss_cd_disc_type_t degauss_cd_directory_type(const uint8_t *sector,
	size_t size)
{
	if (contains_bytes(sector, size, "IPL.TXT", 7)) return DEGAUSS_CD_NEOGEOCD;
	if (contains_bytes(sector, size, "CDI_APPL", 8)) return DEGAUSS_CD_CDI;
	return DEGAUSS_CD_NONE;
}

degauss_cd_disc_type_t degauss_cd_raw_type(const uint8_t *sectors,
	size_t size)
{
	return contains_bytes(sectors, size, "PC Engine CD-ROM SYSTEM", 23) ?
		DEGAUSS_CD_PCECD : DEGAUSS_CD_NONE;
}

bool degauss_cd_can_reuse_handled(uint32_t handled_fingerprint,
	uint32_t handled_toc_fingerprint, uint32_t current_toc_fingerprint,
	bool media_changed)
{
	return handled_fingerprint && handled_toc_fingerprint &&
		handled_toc_fingerprint == current_toc_fingerprint && !media_changed;
}

const char *degauss_cd_provider_mgl_name(degauss_cd_provider_kind_t provider,
	degauss_cd_disc_type_t type)
{
	if (provider == DEGAUSS_CD_PROVIDER_ANIME)
	{
		switch (type)
		{
		case DEGAUSS_CD_MEGACD: return "MegaCD.mgl";
		case DEGAUSS_CD_SATURN: return "Saturn.mgl";
		case DEGAUSS_CD_PSX: return "PSX.mgl";
		case DEGAUSS_CD_PCECD: return "TurboGrafx16-CD.mgl";
		case DEGAUSS_CD_NEOGEOCD: return "NeoGeoCD.mgl";
		case DEGAUSS_CD_3DO: return "3DO.mgl";
		case DEGAUSS_CD_CDI: return "CDi.mgl";
		case DEGAUSS_CD_MDPLUS: return "MDPlus.mgl";
		case DEGAUSS_CD_SNES_MSU1: return "SNES-MSU1.mgl";
		default: return NULL;
		}
	}

	switch (type)
	{
	case DEGAUSS_CD_MEGACD: return "Mega CD.mgl";
	case DEGAUSS_CD_SATURN: return "Saturn.mgl";
	case DEGAUSS_CD_PSX: return "PlayStation.mgl";
	case DEGAUSS_CD_PCECD: return "TurboGrafx-CD.mgl";
	case DEGAUSS_CD_NEOGEOCD: return "Neo Geo CD.mgl";
	case DEGAUSS_CD_3DO: return "3DO.mgl";
	case DEGAUSS_CD_CDI: return "Philips CD-i.mgl";
	default: return NULL;
	}
}

const char *degauss_cd_disc_type_name(degauss_cd_disc_type_t type)
{
	switch (type)
	{
	case DEGAUSS_CD_MEGACD: return "Mega CD";
	case DEGAUSS_CD_SATURN: return "Saturn";
	case DEGAUSS_CD_PSX: return "PlayStation";
	case DEGAUSS_CD_PCECD: return "PC Engine CD";
	case DEGAUSS_CD_NEOGEOCD: return "Neo Geo CD";
	case DEGAUSS_CD_3DO: return "3DO";
	case DEGAUSS_CD_CDI: return "CD-i";
	case DEGAUSS_CD_MDPLUS: return "MD+";
	case DEGAUSS_CD_SNES_MSU1: return "SNES MSU-1";
	case DEGAUSS_CD_AUDIO: return "Audio CD";
	default: return "unknown CD";
	}
}
