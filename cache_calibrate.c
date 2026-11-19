#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>

#define N 2000
#define EVICT_SIZE (4 * 1024 * 1024)

static volatile unsigned char sink;

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static int cmp(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a;
    uint64_t y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

int main(void) {
    int fd = open("/mnt/shared/probe.bin", O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }

    volatile unsigned char *p =
        mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, 0);

    if (p == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 1;
    }
    close(fd);

    unsigned char *evict = malloc(EVICT_SIZE);
    if (!evict) return 1;

    for (size_t j = 0; j < EVICT_SIZE; j += 64)
        evict[j] = (unsigned char)j;

    uint64_t cold[N], hot[N];
    sink ^= p[0];

    for (int i = 0; i < N; i++) {
        for (size_t j = 0; j < EVICT_SIZE; j += 64)
            sink ^= evict[j];

        __asm__ volatile("dsb sy" ::: "memory");

        uint64_t t = now_ns();
        sink ^= p[0];
        __asm__ volatile("dsb sy" ::: "memory");
        cold[i] = now_ns() - t;

        t = now_ns();
        sink ^= p[0];
        __asm__ volatile("dsb sy" ::: "memory");
        hot[i] = now_ns() - t;
    }

    qsort(cold, N, sizeof(uint64_t), cmp);
    qsort(hot, N, sizeof(uint64_t), cmp);

    printf("Cold median: %llu ns\n",
        (unsigned long long)cold[N / 2]);
    printf("Hot median:  %llu ns\n",
        (unsigned long long)hot[N / 2]);

    munmap((void *)p, 4096);
    free(evict);
    return 0;
}
