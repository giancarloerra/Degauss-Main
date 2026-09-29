#include "physical_cd_autorun.h"

// Disc signatures and raw-read fallbacks come from Zaparoo Main's working
// physical-disc implementation, itself adapted from
// Anime0t4ku/Main_MiSTer_Physical_Disc.

#include <errno.h>
#include <fcntl.h>
#include <linux/cdrom.h>
#include <limits.h>
#include <pthread.h>
#include <scsi/sg.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "file_io.h"
#include "hardware.h"
#include "menu.h"
#include "physical_cd_logic.h"
#include "user_io.h"

#define CD_RAW_SECTOR_SIZE 2352
#define CD_USER_SECTOR_SIZE 2048
#define CD_MAX_TRACKS 100
#define CD_POLL_MS 1000
#define CD_READ_TIMEOUT_MS 2000
#define CD_UNREADABLE_FINGERPRINT 0xFFFFFFFFu
#define CD_CONTROL_POLL_MS 100
#define DEGAUSS_PHYSICAL_DISC_CONTROL_FILE "/tmp/degauss_physical_disc.pid"
#define DEGAUSS_PHYSICAL_DISC_EVENT_FILE "/tmp/degauss_physical_disc_event"
#define DEGAUSS_PHYSICAL_DISC_HANDLED_FILE "/tmp/degauss_physical_disc_handled"

typedef struct
{
	int start;
	int end;
	bool data;
} cd_track_t;

typedef struct
{
	cd_track_t tracks[CD_MAX_TRACKS];
	int count;
	int leadout;
	int first_data;
} cd_toc_t;

typedef struct
{
	bool present;
	bool confirmed_absent;
	bool media_changed;
	bool readable;
	bool classified;
	uint32_t fingerprint;
	degauss_cd_disc_type_t type;
} cd_detection_t;

typedef struct
{
	unsigned int generation;
	uint32_t handled_fingerprint;
} cd_worker_args_t;

typedef struct
{
	degauss_cd_provider_kind_t kind;
	const char *name;
	const char *binary;
	const char *mgl_dir;
} cd_provider_t;

static const cd_provider_t s_providers[] =
{
	{DEGAUSS_CD_PROVIDER_ANIME, "Physical Disc Support",
		"/media/fat/MiSTer_Physical-CD", "/media/fat/_Physical Disc Cores"},
	{DEGAUSS_CD_PROVIDER_MISTER_DISC, "mister-disc",
		"/media/fat/MiSTer-disc", "/media/fat/_Disc_Cores"},
};

static pthread_mutex_t s_lock = PTHREAD_MUTEX_INITIALIZER;
static bool s_poll_active = false;
static bool s_active = false;
static bool s_worker_running = false;
static bool s_result_ready = false;
static unsigned int s_generation = 0;
static cd_detection_t s_result;
static uint32_t s_handled_fingerprint = 0;
static bool s_handled_loaded = false;
static int s_retry_count = 0;
static int s_absent_count = 0;
static unsigned long s_poll_timer = 0;
static unsigned long s_control_poll_timer = 0;

static uint32_t read_le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
		((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t hash_bytes(uint32_t hash, const uint8_t *data, size_t size)
{
	for (size_t i = 0; i < size; i++) hash = (hash ^ data[i]) * 16777619u;
	return hash;
}

static bool control_process_alive(void)
{
	FILE *file = fopen(DEGAUSS_PHYSICAL_DISC_CONTROL_FILE, "r");
	if (!file) return false;

	unsigned int version = 0;
	long pid = 0;
	char trailing = 0;
	int fields = fscanf(file, "%u %ld %c", &version, &pid, &trailing);
	fclose(file);
	if (fields != 2 || version != 1 || pid <= 1 || pid > INT_MAX) return false;
	return kill((pid_t)pid, 0) == 0 || errno == EPERM;
}

static bool write_all(int fd, const char *data, size_t size)
{
	while (size)
	{
		ssize_t written = write(fd, data, size);
		if (written < 0 && errno == EINTR) continue;
		if (written <= 0) return false;
		data += written;
		size -= written;
	}
	return true;
}

static bool write_event(const char *kind, const char *value)
{
	if (!kind || !value || strchr(kind, '\n') || strchr(value, '\n')) return false;
	if (access(DEGAUSS_PHYSICAL_DISC_EVENT_FILE, F_OK) == 0) return false;

	char body[PATH_MAX + 64];
	int length = snprintf(body, sizeof(body), "%s\n%s\n", kind, value);
	if (length <= 0 || (size_t)length >= sizeof(body)) return false;

	char temporary[PATH_MAX];
	int temp_length = snprintf(temporary, sizeof(temporary), "%s.part.%ld",
		DEGAUSS_PHYSICAL_DISC_EVENT_FILE, (long)getpid());
	if (temp_length <= 0 || (size_t)temp_length >= sizeof(temporary)) return false;

	int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
	if (fd < 0) return false;
	bool written = write_all(fd, body, (size_t)length);
	if (close(fd)) written = false;
	if (written && !rename(temporary, DEGAUSS_PHYSICAL_DISC_EVENT_FILE)) return true;
	unlink(temporary);
	return false;
}

static bool detection_current(unsigned int generation)
{
	pthread_mutex_lock(&s_lock);
	bool current = s_active && generation == s_generation;
	pthread_mutex_unlock(&s_lock);
	return current;
}

static void load_handled_fingerprint(void)
{
	if (s_handled_loaded) return;
	s_handled_loaded = true;

	FILE *file = fopen(DEGAUSS_PHYSICAL_DISC_HANDLED_FILE, "r");
	if (!file) return;
	fscanf(file, "%x", &s_handled_fingerprint);
	fclose(file);
}

static bool save_handled_fingerprint(uint32_t fingerprint)
{
	if (!fingerprint)
	{
		if (unlink(DEGAUSS_PHYSICAL_DISC_HANDLED_FILE) && errno != ENOENT) return false;
		s_handled_fingerprint = 0;
		return true;
	}

	FILE *file = fopen(DEGAUSS_PHYSICAL_DISC_HANDLED_FILE, "w");
	if (!file) return false;
	bool saved = fprintf(file, "%08x\n", fingerprint) == 9;
	if (fclose(file)) saved = false;
	if (saved) s_handled_fingerprint = fingerprint;
	return saved;
}

static int open_disc_drive(bool *confirmed_absent)
{
	char path[32];
	*confirmed_absent = false;
	bool saw_no_disc = false;
	bool saw_uncertain = false;

	for (int i = 0; i < 8; i++)
	{
		snprintf(path, sizeof(path), "/dev/sr%d", i);
		int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
		{
			if (errno != ENOENT && errno != ENODEV) saw_uncertain = true;
			continue;
		}

		int status = ioctl(fd, CDROM_DRIVE_STATUS, CDSL_CURRENT);
		if (status == CDS_DISC_OK) return fd;
		if (status == CDS_NO_DISC || status == CDS_TRAY_OPEN) saw_no_disc = true;
		else saw_uncertain = true;
		close(fd);
	}

	*confirmed_absent = saw_no_disc && !saw_uncertain;
	return -1;
}

static int read_raw_scsi(int fd, int lba, uint8_t *dst)
{
	uint8_t cdb[12] = {};
	uint8_t sense[32] = {};
	struct sg_io_hdr io = {};

	cdb[0] = 0xBE; // READ CD
	cdb[2] = (lba >> 24) & 0xFF;
	cdb[3] = (lba >> 16) & 0xFF;
	cdb[4] = (lba >> 8) & 0xFF;
	cdb[5] = lba & 0xFF;
	cdb[8] = 1;
	cdb[9] = 0xF8; // sync, header, user data and EDC/ECC

	io.interface_id = 'S';
	io.cmd_len = sizeof(cdb);
	io.cmdp = cdb;
	io.dxfer_direction = SG_DXFER_FROM_DEV;
	io.dxfer_len = CD_RAW_SECTOR_SIZE;
	io.dxferp = dst;
	io.sbp = sense;
	io.mx_sb_len = sizeof(sense);
	io.timeout = CD_READ_TIMEOUT_MS;

	if (ioctl(fd, SG_IO, &io) < 0) return -1;
	if (io.status || io.host_status || io.driver_status || io.resid != 0) return -1;
	if ((io.info & SG_INFO_OK_MASK) != SG_INFO_OK) return -1;
	return 0;
}

static int read_raw_ioctl(int fd, int lba, uint8_t *dst)
{
	union
	{
		struct cdrom_msf msf;
		uint8_t raw[CD_RAW_SECTOR_SIZE];
	} req;

	int frame = lba + 150;
	memset(&req, 0, sizeof(req));
	req.msf.cdmsf_min0 = frame / (75 * 60);
	req.msf.cdmsf_sec0 = (frame / 75) % 60;
	req.msf.cdmsf_frame0 = frame % 75;

	if (ioctl(fd, CDROMREADRAW, &req) < 0) return -1;
	memcpy(dst, req.raw, CD_RAW_SECTOR_SIZE);
	return 0;
}

static int read_raw_sector(int fd, int lba, uint8_t *dst)
{
	if (!read_raw_scsi(fd, lba, dst)) return 0;
	return read_raw_ioctl(fd, lba, dst);
}

static int read_user_sector(int fd, int lba, uint8_t *dst)
{
	uint8_t raw[CD_RAW_SECTOR_SIZE];
	if (!read_raw_sector(fd, lba, raw))
	{
		int offset = raw[15] == 2 ? 24 : 16;
		memcpy(dst, raw + offset, CD_USER_SECTOR_SIZE);
		return 0;
	}

	ssize_t count = pread(fd, dst, CD_USER_SECTOR_SIZE,
		(off_t)lba * CD_USER_SECTOR_SIZE);
	return count == CD_USER_SECTOR_SIZE ? 0 : -1;
}

static int read_toc(int fd, cd_toc_t *toc)
{
	struct cdrom_tochdr hdr = {};
	if (ioctl(fd, CDROMREADTOCHDR, &hdr) < 0) return -1;

	memset(toc, 0, sizeof(*toc));
	toc->first_data = -1;

	for (int track = hdr.cdth_trk0;
		track <= hdr.cdth_trk1 && toc->count < CD_MAX_TRACKS;
		track++)
	{
		struct cdrom_tocentry entry = {};
		entry.cdte_track = track;
		entry.cdte_format = CDROM_LBA;
		if (ioctl(fd, CDROMREADTOCENTRY, &entry) < 0) return -1;

		cd_track_t *out = &toc->tracks[toc->count];
		out->start = entry.cdte_addr.lba;
		out->data = (entry.cdte_ctrl & CDROM_DATA_TRACK) != 0;
		if (out->data && toc->first_data < 0) toc->first_data = out->start;
		if (toc->count) toc->tracks[toc->count - 1].end = out->start;
		toc->count++;
	}

	if (!toc->count) return -1;

	struct cdrom_tocentry leadout = {};
	leadout.cdte_track = CDROM_LEADOUT;
	leadout.cdte_format = CDROM_LBA;
	if (ioctl(fd, CDROMREADTOCENTRY, &leadout) < 0) return -1;

	toc->leadout = leadout.cdte_addr.lba;
	toc->tracks[toc->count - 1].end = toc->leadout;
	return 0;
}

static uint32_t toc_fingerprint(const cd_toc_t *toc)
{
	uint32_t hash = 2166136261u;
	hash = (hash ^ (uint32_t)toc->count) * 16777619u;
	hash = (hash ^ (uint32_t)toc->leadout) * 16777619u;

	for (int i = 0; i < toc->count; i++)
	{
		hash = (hash ^ (uint32_t)toc->tracks[i].start) * 16777619u;
		hash = (hash ^ (uint32_t)toc->tracks[i].end) * 16777619u;
		hash = (hash ^ (uint32_t)toc->tracks[i].data) * 16777619u;
	}

	return hash;
}

static int iso_root_features(int fd, int base, unsigned int generation,
	bool *has_mdplus, bool *has_snes, uint32_t *fingerprint)
{
	uint8_t pvd[CD_USER_SECTOR_SIZE];
	*has_mdplus = false;
	*has_snes = false;

	if (!detection_current(generation)) return -1;
	if (read_user_sector(fd, base + 16, pvd)) return -1;
	*fingerprint = hash_bytes(*fingerprint, pvd, sizeof(pvd));
	if (pvd[0] != 1 || memcmp(pvd + 1, "CD001", 5)) return 0;

	const uint8_t *root = pvd + 156;
	if (root[0] < 34) return 1;
	uint32_t extent = read_le32(root + 2);
	uint32_t size = read_le32(root + 10);
	if (!extent || !size) return 1;

	char md_names[64][128];
	char cue_names[64][128];
	int md_count = 0;
	int cue_count = 0;
	uint32_t done = 0;

	while (done < size && done < 1024 * 1024)
	{
		if (!detection_current(generation)) return -1;

		uint8_t sector[CD_USER_SECTOR_SIZE];
		if (read_user_sector(fd, base + extent + done / CD_USER_SECTOR_SIZE, sector)) return -1;
		*fingerprint = hash_bytes(*fingerprint, sector, sizeof(sector));

		int offset = 0;
		while (offset < CD_USER_SECTOR_SIZE && done + offset < size)
		{
			int length = sector[offset];
			if (!length) break;
			if (length < 34 || offset + length > CD_USER_SECTOR_SIZE) break;

			int name_length = sector[offset + 32];
			if (name_length > 0 && name_length < 120 && offset + 33 + name_length <= CD_USER_SECTOR_SIZE)
			{
				char name[128];
				memcpy(name, sector + offset + 33, name_length);
				name[name_length] = 0;
				char *version = strchr(name, ';');
				if (version) *version = 0;
				char *extension = strrchr(name, '.');

				if (extension && (!strcasecmp(extension, ".sfc") || !strcasecmp(extension, ".smc")))
					*has_snes = true;
				else if (extension && !strcasecmp(extension, ".md") && md_count < 64)
				{
					*extension = 0;
					snprintf(md_names[md_count++], sizeof(md_names[0]), "%s", name);
				}
				else if (extension && !strcasecmp(extension, ".cue") && cue_count < 64)
				{
					*extension = 0;
					snprintf(cue_names[cue_count++], sizeof(cue_names[0]), "%s", name);
				}
			}

			offset += length;
		}

		done += CD_USER_SECTOR_SIZE;
	}

	for (int i = 0; i < md_count; i++)
	{
		for (int j = 0; j < cue_count; j++)
		{
			if (!strcasecmp(md_names[i], cue_names[j]))
			{
				*has_mdplus = true;
				return 1;
			}
		}
	}

	return 1;
}

static degauss_cd_disc_type_t identify_disc(int fd, const cd_toc_t *toc,
	unsigned int generation, uint32_t *fingerprint, bool *complete)
{
	*complete = false;
	degauss_cd_disc_type_t type = degauss_cd_initial_type(toc->first_data >= 0, false);
	if (type != DEGAUSS_CD_NONE)
	{
		*complete = true;
		return type;
	}

	int base = toc->first_data;
	bool has_mdplus = false;
	bool has_snes = false;
	bool io_failed = iso_root_features(fd, base, generation,
		&has_mdplus, &has_snes, fingerprint) < 0;
	if (!detection_current(generation)) return DEGAUSS_CD_NONE;
	type = degauss_cd_initial_type(true, has_mdplus);
	if (type != DEGAUSS_CD_NONE)
	{
		*complete = true;
		return type;
	}

	uint8_t sector[CD_USER_SECTOR_SIZE];
	if (!read_user_sector(fd, base, sector))
	{
		*fingerprint = hash_bytes(*fingerprint, sector, sizeof(sector));
		type = degauss_cd_sector_zero_type(sector, sizeof(sector));
		if (type != DEGAUSS_CD_NONE)
		{
			*complete = true;
			return type;
		}
	}
	else
	{
		io_failed = true;
	}

	if (!detection_current(generation)) return DEGAUSS_CD_NONE;
	if (!read_user_sector(fd, base + 16, sector))
	{
		*fingerprint = hash_bytes(*fingerprint, sector, sizeof(sector));
		type = degauss_cd_pvd_type(sector, sizeof(sector));
		if (type != DEGAUSS_CD_NONE)
		{
			*complete = true;
			return type;
		}
	}
	else
	{
		io_failed = true;
	}

	for (int offset = 16; offset <= 40; offset++)
	{
		if (!detection_current(generation)) return DEGAUSS_CD_NONE;
		if (read_user_sector(fd, base + offset, sector))
		{
			io_failed = true;
			continue;
		}
		*fingerprint = hash_bytes(*fingerprint, sector, sizeof(sector));
		type = degauss_cd_directory_type(sector, sizeof(sector));
		if (type != DEGAUSS_CD_NONE)
		{
			*complete = true;
			return type;
		}
	}

	if (!detection_current(generation)) return DEGAUSS_CD_NONE;
	uint8_t raw[CD_RAW_SECTOR_SIZE * 2];
	int raw_error = read_raw_sector(fd, base, raw);
	if (!raw_error && !detection_current(generation)) return DEGAUSS_CD_NONE;
	if (!raw_error)
		raw_error = read_raw_sector(fd, base + 1, raw + CD_RAW_SECTOR_SIZE);
	if (!raw_error)
	{
		*fingerprint = hash_bytes(*fingerprint, raw, sizeof(raw));
		type = degauss_cd_raw_type(raw, sizeof(raw));
		if (type != DEGAUSS_CD_NONE)
		{
			*complete = true;
			return type;
		}
	}
	else
	{
		io_failed = true;
	}

	type = degauss_cd_final_type(has_snes);
	if (type == DEGAUSS_CD_SNES_MSU1)
	{
		*complete = true;
		return type;
	}
	if (!io_failed) *complete = true;
	return type;
}

static cd_detection_t detect_disc(unsigned int generation,
	uint32_t handled_fingerprint)
{
	cd_detection_t result = {};
	if (!detection_current(generation)) return result;

	int fd = open_disc_drive(&result.confirmed_absent);
	if (fd < 0) return result;
	result.present = true;

	if (!detection_current(generation))
	{
		close(fd);
		return result;
	}

	int media_changed = ioctl(fd, CDROM_MEDIA_CHANGED, CDSL_CURRENT);
	if (handled_fingerprint && media_changed == 0)
	{
		result.readable = true;
		result.classified = true;
		result.fingerprint = handled_fingerprint;
		close(fd);
		return result;
	}
	result.media_changed = handled_fingerprint && media_changed > 0;

	cd_toc_t toc;
	if (!read_toc(fd, &toc))
	{
		result.readable = true;
		result.fingerprint = toc_fingerprint(&toc);
		result.type = identify_disc(fd, &toc, generation,
			&result.fingerprint, &result.classified);
	}

	close(fd);
	return result;
}

static void *detection_worker(void *arg)
{
	cd_worker_args_t args = *(cd_worker_args_t *)arg;
	free(arg);
	cd_detection_t result = detect_disc(args.generation,
		args.handled_fingerprint);

	pthread_mutex_lock(&s_lock);
	if (s_active && args.generation == s_generation)
	{
		s_result = result;
		s_result_ready = true;
	}
	s_worker_running = false;
	pthread_mutex_unlock(&s_lock);
	return NULL;
}

static void start_detection(void)
{
	cd_worker_args_t *args = (cd_worker_args_t *)malloc(sizeof(*args));
	if (!args) return;

	pthread_mutex_lock(&s_lock);
	if (s_worker_running)
	{
		pthread_mutex_unlock(&s_lock);
		free(args);
		return;
	}

	s_worker_running = true;
	args->generation = s_generation;
	args->handled_fingerprint = s_handled_fingerprint;
	pthread_mutex_unlock(&s_lock);

	pthread_t worker;
	if (pthread_create(&worker, NULL, detection_worker, args))
	{
		pthread_mutex_lock(&s_lock);
		s_worker_running = false;
		pthread_mutex_unlock(&s_lock);
		free(args);
		return;
	}
	pthread_detach(worker);
}

static bool take_result(cd_detection_t *result)
{
	bool ready;
	pthread_mutex_lock(&s_lock);
	ready = s_result_ready;
	if (ready)
	{
		*result = s_result;
		s_result_ready = false;
	}
	pthread_mutex_unlock(&s_lock);
	return ready;
}

static void set_active(bool active)
{
	if (s_poll_active == active) return;
	s_poll_active = active;
	if (active) load_handled_fingerprint();

	pthread_mutex_lock(&s_lock);
	s_active = active;
	s_generation++;
	s_result_ready = false;
	pthread_mutex_unlock(&s_lock);

	if (!active)
	{
		s_poll_timer = 0;
		s_absent_count = 0;
		s_retry_count = 0;
	}
}

static bool resolve_disc_launcher(degauss_cd_disc_type_t type, char *path,
	size_t path_size, const char **provider_name, bool *provider_installed)
{
	*provider_installed = false;
	for (size_t i = 0; i < sizeof(s_providers) / sizeof(s_providers[0]); i++)
	{
		const cd_provider_t *provider = &s_providers[i];
		if (!FileExists(provider->binary, 0)) continue;
		*provider_installed = true;

		const char *mgl = degauss_cd_provider_mgl_name(provider->kind, type);
		if (!mgl) continue;
		snprintf(path, path_size, "%s/%s", provider->mgl_dir, mgl);
		if (!FileExists(path, 0)) continue;

		*provider_name = provider->name;
		return true;
	}
	return false;
}

static bool queue_handled_event(uint32_t fingerprint, const char *kind,
	const char *value)
{
	if (!save_handled_fingerprint(fingerprint)) return false;
	if (write_event(kind, value)) return true;
	if (!save_handled_fingerprint(0))
		printf("CD autorun: unable to clear handled state after event failure\n");
	return false;
}

// Returns true when this poll cycle must not queue another worker.
static bool consume_detection(const cd_detection_t *result)
{
	if (!result->present)
	{
		if (result->confirmed_absent)
		{
			if (++s_absent_count >= 2) save_handled_fingerprint(0);
		}
		else s_absent_count = 0;
		s_retry_count = 0;
		return false;
	}

	s_absent_count = 0;
	if (result->media_changed) save_handled_fingerprint(0);

	if (!result->readable || !result->classified || !result->fingerprint)
	{
		if (s_retry_count >= 4)
		{
			uint32_t fingerprint = result->fingerprint ?
				result->fingerprint : CD_UNREADABLE_FINGERPRINT;
			save_handled_fingerprint(fingerprint);
			s_retry_count = 0;
			printf("CD autorun: disc could not be identified; waiting for media change\n");
			return false;
		}

		int delay = CD_POLL_MS << (s_retry_count < 2 ? s_retry_count : 2);
		s_retry_count++;
		s_poll_timer = GetTimer(delay);
		return true;
	}

	s_retry_count = 0;
	if (result->fingerprint == s_handled_fingerprint) return false;
	if (result->type == DEGAUSS_CD_AUDIO || result->type == DEGAUSS_CD_UNKNOWN)
	{
		save_handled_fingerprint(result->fingerprint);
		printf("CD autorun: ignoring %s\n", degauss_cd_disc_type_name(result->type));
		return false;
	}

	char path[512];
	const char *provider_name = NULL;
	bool provider_installed;
	if (!resolve_disc_launcher(result->type, path, sizeof(path),
		&provider_name, &provider_installed))
	{
		char message[256];
		if (!provider_installed)
		{
			printf("CD autorun: no physical CD provider installed for %s\n",
				degauss_cd_disc_type_name(result->type));
			snprintf(message, sizeof(message),
				"No physical CD provider is installed for %s.",
				degauss_cd_disc_type_name(result->type));
		}
		else
		{
			printf("CD autorun: installed provider has no launcher for %s\n",
				degauss_cd_disc_type_name(result->type));
			snprintf(message, sizeof(message),
				"The installed physical CD provider has no %s launcher.",
				degauss_cd_disc_type_name(result->type));
		}
		if (!queue_handled_event(result->fingerprint, "error", message))
			printf("CD autorun: unable to report provider error\n");
		return false;
	}

	if (!queue_handled_event(result->fingerprint, "launch", path))
	{
		printf("CD autorun: unable to queue launch for %s\n", path);
		write_event("error", "Physical disc launch could not be prepared.");
		return true;
	}

	printf("CD autorun: detected %s, launching %s provider: %s\n",
		degauss_cd_disc_type_name(result->type), provider_name, path);
	return true;
}

void physical_cd_autorun_poll(void)
{
	if (!is_menu())
	{
		set_active(false);
		s_control_poll_timer = 0;
		return;
	}
	if (!s_control_poll_timer || CheckTimer(s_control_poll_timer))
	{
		s_control_poll_timer = GetTimer(CD_CONTROL_POLL_MS);
		set_active(control_process_alive());
	}
	if (!s_poll_active) return;

	if (s_poll_timer && !CheckTimer(s_poll_timer)) return;
	s_poll_timer = GetTimer(CD_POLL_MS);

	cd_detection_t result;
	if (take_result(&result))
	{
		if (consume_detection(&result) || !is_menu()) return;
	}

	start_detection();
}
