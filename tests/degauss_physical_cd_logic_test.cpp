#include "support/degauss/physical_cd_logic.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static void put(uint8_t *buffer, size_t offset, const char *text)
{
	memcpy(buffer + offset, text, strlen(text));
}

int main()
{
	uint8_t sector[2048] = {};
	put(sector, 0, "SEGADISCSYSTEM");
	assert(degauss_cd_sector_zero_type(sector, sizeof(sector)) == DEGAUSS_CD_MEGACD);
	memset(sector, 0, sizeof(sector));
	put(sector, 0, "SEGA SEGASATURN");
	assert(degauss_cd_sector_zero_type(sector, sizeof(sector)) == DEGAUSS_CD_SATURN);
	memset(sector, 0, sizeof(sector));
	sector[0] = 0x01;
	memset(sector + 1, 0x5A, 5);
	assert(degauss_cd_sector_zero_type(sector, sizeof(sector)) == DEGAUSS_CD_3DO);

	memset(sector, 0, sizeof(sector));
	put(sector, 1, "CD001");
	put(sector, 8, "PLAYSTATION");
	assert(degauss_cd_pvd_type(sector, sizeof(sector)) == DEGAUSS_CD_PSX);
	memset(sector, 0, sizeof(sector));
	put(sector, 1, "CD001");
	put(sector, 8, "NGCD");
	assert(degauss_cd_pvd_type(sector, sizeof(sector)) == DEGAUSS_CD_NEOGEOCD);
	memset(sector, 0, sizeof(sector));
	put(sector, 1, "CD-I");
	assert(degauss_cd_pvd_type(sector, sizeof(sector)) == DEGAUSS_CD_CDI);

	memset(sector, 0, sizeof(sector));
	put(sector, 100, "IPL.TXT");
	assert(degauss_cd_directory_type(sector, sizeof(sector)) == DEGAUSS_CD_NEOGEOCD);
	memset(sector, 0, sizeof(sector));
	put(sector, 100, "CDI_APPL");
	assert(degauss_cd_directory_type(sector, sizeof(sector)) == DEGAUSS_CD_CDI);

	uint8_t raw[4704] = {};
	put(raw, 300, "PC Engine CD-ROM SYSTEM");
	assert(degauss_cd_raw_type(raw, sizeof(raw)) == DEGAUSS_CD_PCECD);
	assert(degauss_cd_initial_type(false, false) == DEGAUSS_CD_AUDIO);
	assert(degauss_cd_initial_type(true, true) == DEGAUSS_CD_MDPLUS);
	assert(degauss_cd_initial_type(true, false) == DEGAUSS_CD_NONE);
	assert(degauss_cd_final_type(true) == DEGAUSS_CD_SNES_MSU1);
	assert(degauss_cd_final_type(false) == DEGAUSS_CD_UNKNOWN);

	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_MEGACD), "MegaCD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_SATURN), "Saturn.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_PSX), "PSX.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_PCECD), "TurboGrafx16-CD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_NEOGEOCD), "NeoGeoCD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_3DO), "3DO.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_CDI), "CDi.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_MDPLUS), "MDPlus.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_SNES_MSU1), "SNES-MSU1.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_MEGACD), "Mega CD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_SATURN), "Saturn.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_PSX), "PlayStation.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_PCECD), "TurboGrafx-CD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_NEOGEOCD), "Neo Geo CD.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_3DO), "3DO.mgl"));
	assert(!strcmp(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_CDI), "Philips CD-i.mgl"));
	assert(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_MDPLUS) == NULL);
	assert(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_MISTER_DISC,
		DEGAUSS_CD_SNES_MSU1) == NULL);
	assert(degauss_cd_provider_mgl_name(DEGAUSS_CD_PROVIDER_ANIME,
		DEGAUSS_CD_AUDIO) == NULL);
	assert(!strcmp(degauss_cd_disc_type_name(DEGAUSS_CD_NEOGEOCD), "Neo Geo CD"));
	return 0;
}
