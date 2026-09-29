#pragma once

#include <stddef.h>
#include <stdint.h>

typedef enum
{
	DEGAUSS_CD_NONE = 0,
	DEGAUSS_CD_MEGACD,
	DEGAUSS_CD_SATURN,
	DEGAUSS_CD_PSX,
	DEGAUSS_CD_PCECD,
	DEGAUSS_CD_NEOGEOCD,
	DEGAUSS_CD_3DO,
	DEGAUSS_CD_CDI,
	DEGAUSS_CD_MDPLUS,
	DEGAUSS_CD_SNES_MSU1,
	DEGAUSS_CD_AUDIO,
	DEGAUSS_CD_UNKNOWN,
} degauss_cd_disc_type_t;

typedef enum
{
	DEGAUSS_CD_PROVIDER_ANIME,
	DEGAUSS_CD_PROVIDER_MISTER_DISC,
} degauss_cd_provider_kind_t;

degauss_cd_disc_type_t degauss_cd_initial_type(bool has_data_track,
	bool has_mdplus);
degauss_cd_disc_type_t degauss_cd_final_type(bool has_snes_rom);
degauss_cd_disc_type_t degauss_cd_sector_zero_type(const uint8_t *sector,
	size_t size);
degauss_cd_disc_type_t degauss_cd_pvd_type(const uint8_t *sector,
	size_t size);
degauss_cd_disc_type_t degauss_cd_directory_type(const uint8_t *sector,
	size_t size);
degauss_cd_disc_type_t degauss_cd_raw_type(const uint8_t *sectors,
	size_t size);
bool degauss_cd_can_reuse_handled(uint32_t handled_fingerprint,
	uint32_t handled_toc_fingerprint, uint32_t current_toc_fingerprint,
	bool media_changed);
const char *degauss_cd_provider_mgl_name(degauss_cd_provider_kind_t provider,
	degauss_cd_disc_type_t type);
const char *degauss_cd_disc_type_name(degauss_cd_disc_type_t type);
