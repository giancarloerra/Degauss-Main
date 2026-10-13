// Mac SCSI family hard disks: write buffer.
// Each O_SYNC write costs ~4 ms, so gather sectors into runs and write them out together.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

#include "../../hardware.h"
#include "../../file_io.h"
#include "../../user_io.h"
#include "../../spi.h"
#include "mac.h"
#include "mac_disk.h"

#define BLKSZ    512
#define SLOTS    2
#define RUN_MAX  (64 * 1024)
#define RUNS     8
#define IDLE_MS  20
#define AGE_MS   500

struct run { uint64_t off; uint32_t len; unsigned long born, last; uint8_t data[RUN_MAX]; };

struct slot
{
	run           *runs;
	int            pending;
	unsigned long  last;
	unsigned long  retry;
	fileTYPE      *f;
	dev_t          dev;
	ino_t          ino;
	char           path[1024];
};

static slot slots[SLOTS];
static int  pending;

static int flush_run(int disk, run *r)
{
	slot *s = &slots[disk];
	uint32_t len = r->len;
	if (!len) return 1;
	if (s->retry && !CheckTimer(s->retry)) return 0;
	diskled_on();

	int ok = 0;
	errno = 0;
	struct stat64 st;
	if (s->f->filp && !fstat64(fileno(s->f->filp), &st) && st.st_dev == s->dev && st.st_ino == s->ino)
	{
		clearerr(s->f->filp);
		ok = FileSeek(s->f, r->off, SEEK_SET) && FileWriteAdv(s->f, r->data, len) == (int)len;
	}
	else
	{
		// slot was remounted: write to the previous image
		int fd = open(s->path, O_WRONLY | O_SYNC | O_CLOEXEC);
		if (fd >= 0)
		{
			if (!fstat64(fd, &st))
			{
				if (st.st_dev == s->dev && st.st_ino == s->ino) ok = pwrite64(fd, r->data, len, r->off) == (ssize_t)len;
				else errno = ESTALE;
			}
			int error = errno;
			if (close(fd) && ok) { ok = 0; error = errno; }
			errno = error;
		}
	}
	if (!ok)
	{
		printf("mac_disk: write %u @ %llu to %s failed: %s\n", len, (unsigned long long)r->off, s->path, strerror(errno ? errno : EIO));
		s->retry = GetTimer(1000);
		return 0;
	}
	s->retry = 0;
	r->len = 0;
	s->pending--;
	pending--;
	return 1;
}

static int flush_overlap(int disk, uint64_t off, uint64_t len, run *keep)
{
	if (!slots[disk].pending) return 1;
	for (int i = 0; i < RUNS; i++)
	{
		run *r = &slots[disk].runs[i];
		if (r != keep && r->len && off < r->off + r->len && r->off < off + len && !flush_run(disk, r)) return 0;
	}
	return 1;
}

int mac_disk_flush(int disk)
{
	if (disk < 0 || disk >= SLOTS) return 1;
	while (slots[disk].pending)
	{
		run *lo = 0;
		for (int i = 0; i < RUNS; i++)
		{
			run *r = &slots[disk].runs[i];
			if (r->len && (!lo || r->off < lo->off)) lo = r;
		}
		if (!flush_run(disk, lo)) return 0;
	}
	return 1;
}

void mac_disk_poll()
{
	if (!pending) return;

	unsigned long now = GetTimer(0);
	for (int d = 0; d < SLOTS; d++)
	{
		slot *s = &slots[d];
		if (!s->pending) continue;
		if (now - s->last >= IDLE_MS)
		{
			mac_disk_flush(d);
			continue;
		}
		for (int i = 0; i < RUNS; i++)
			if (s->runs[i].len && now - s->runs[i].born >= AGE_MS) flush_run(d, &s->runs[i]);
	}
}

static int can_buffer(int disk, fileTYPE *f, uint64_t off, int sz)
{
	slot *s = &slots[disk];
	if (!f->filp || f->type == 2 || (f->mode & O_ACCMODE) == O_RDONLY) return 0;
	if (sz <= 0 || sz > RUN_MAX || off + sz > (uint64_t)f->size) return 0;

	if (!s->runs && !(s->runs = (run*)calloc(RUNS, sizeof(run)))) return 0;

	if (!s->pending)
	{
		struct stat64 st;
		if (fstat64(fileno(f->filp), &st)) return 0;
		s->f = f;
		s->dev = st.st_dev;
		s->ino = st.st_ino;
		snprintf(s->path, sizeof(s->path), "%s", f->path);
	}
	// Reserve room before the SPI write acknowledgement accepts new bytes.
	run *lru = 0;
	for (int i = 0; i < RUNS; i++)
	{
		run *r = &s->runs[i];
		if (!r->len) continue;
		if (off >= r->off && off + sz <= r->off + r->len) return 1;
		if (off == r->off + r->len && r->len + sz <= RUN_MAX) return flush_overlap(disk, off, sz, r) ? 1 : -1;
		if (!lru || r->last < lru->last) lru = r;
	}
	if (!flush_overlap(disk, off, sz, 0)) return -1;
	if (s->pending == RUNS && !flush_run(disk, lru)) return -1;
	return 1;
}

static void stage(int disk, uint64_t off, const uint8_t *data, uint32_t sz)
{
	slot *s = &slots[disk];
	unsigned long now = GetTimer(0);
	run *free_r = 0;

	s->last = now;
	for (int i = 0; i < RUNS; i++)
	{
		run *r = &s->runs[i];
		if (!r->len)
		{
			if (!free_r) free_r = r;
			continue;
		}
		if (off >= r->off && off + sz <= r->off + r->len)
		{
			memcpy(r->data + (off - r->off), data, sz);
			r->last = now;
			return;
		}
		if (off == r->off + r->len && r->len + sz <= RUN_MAX)
		{
			memcpy(r->data + r->len, data, sz);
			r->len += sz;
			r->last = now;
			if (r->len == RUN_MAX) flush_run(disk, r);
			return;
		}
	}

	free_r->off = off;
	free_r->len = sz;
	free_r->born = free_r->last = now;
	memcpy(free_r->data, data, sz);
	s->pending++;
	pending++;
	if (free_r->len == RUN_MAX) flush_run(disk, free_r);
}

int mac_disk_service(int disk, fileTYPE *f, int op, uint64_t lba, int sz, int ack)
{
	static uint8_t buf[UIO_BUFFER_SIZE];

	if (disk < 0 || disk >= SLOTS || !op || !is_mac_scsi_family()) return 0;

	uint64_t off = lba * BLKSZ;
	if (op != 2)
	{
		// covers the generic read buffer and its read-ahead
		return flush_overlap(disk, off, sz + 2ULL * UIO_BUFFER_SIZE, 0) ? 0 : 1;
	}

	int buffered = sz > (int)sizeof(buf) ? 0 : can_buffer(disk, f, off, sz);
	if (buffered < 0) return 1;
	if (!buffered)
	{
		if (!mac_disk_flush(disk)) return 1;
		return 0;
	}

	EnableIO();
	spi_w(UIO_SECTOR_WR | ack);
	spi_block_read(buf, user_io_get_width(), sz);
	DisableIO();

	diskled_on();
	user_io_bufferinvalidate(disk);
	stage(disk, off, buf, sz);
	return 1;
}
