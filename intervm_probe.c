#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>

#define SLOT_SEC 4
#define SLOTS 10
#define MAX_SAMPLES 4000
#define EVICT_BYTES (4 * 1024 * 1024)
static volatile unsigned char sink;
static uint64_t ns(clockid_t c) {
    struct timespec t;
    clock_gettime(c, &t);
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}
static void barrier(void) {
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}
static int compare(const void *a, const void *b) {
    uint64_t x=*(const uint64_t*)a, y=*(const uint64_t*)b;
    return (x>y)-(x<y);
}
int main(int argc, char **argv) {
    if (argc!=3 || (strcmp(argv[1],"victim") && strcmp(argv[1],"observer"))) {
        fprintf(stderr,"Usage: %s victim|observer START_UNIX_SECONDS\n",argv[0]);
        return 1;
    }
    uint64_t start=(uint64_t)strtoull(argv[2],NULL,10)*1000000000ULL;
    int fd=open("/mnt/shared/probe.bin",O_RDONLY);
    if (fd<0) { perror("open probe.bin"); return 1; }
    volatile unsigned char *p=mmap(NULL,8192,PROT_READ,MAP_SHARED,fd,0);
    close(fd);
    if (p==MAP_FAILED) { perror("mmap"); return 1; }
    unsigned char *evict=malloc(EVICT_BYTES);
    if (!evict) return 1;
    for (size_t j=0;j<EVICT_BYTES;j+=64) evict[j]=(unsigned char)j;
    printf("role=%s start=%llu slots=%d slot_seconds=%d\n",argv[1],
           (unsigned long long)(start/1000000000ULL),SLOTS,SLOT_SEC);
    fflush(stdout);
    struct timespec pause={.tv_sec=0,.tv_nsec=5000000};
    while (ns(CLOCK_REALTIME)<start) nanosleep(&pause,NULL);
    if (!strcmp(argv[1],"victim")) {
        int old=-1;
        while (1) {
            uint64_t t=ns(CLOCK_REALTIME);
            if (t>=start+(uint64_t)SLOTS*SLOT_SEC*1000000000ULL) break;
            int slot=(int)((t-start)/(SLOT_SEC*1000000000ULL));
            if (slot!=old) {
                printf("slot=%d offset=%d\n",slot,slot%2?4096:0);
                fflush(stdout);
                old=slot;
            }
            for (size_t j=0;j<128*1024;j+=64) sink^=evict[j];
            sink^=p[slot%2?4096:0];
        }
    } else {
        uint64_t samples[MAX_SAMPLES];
        for (int slot=0; slot<SLOTS; slot++) {
            uint64_t begin=start+(uint64_t)slot*SLOT_SEC*1000000000ULL;
            uint64_t end=begin+(uint64_t)SLOT_SEC*1000000000ULL;
            int count=0;
            while (ns(CLOCK_REALTIME)<end) {
                if (ns(CLOCK_REALTIME)<begin+500000000ULL) continue;
                if (count>=MAX_SAMPLES) { nanosleep(&pause,NULL); continue; }
                for (size_t j=0;j<EVICT_BYTES;j+=64) sink^=evict[j];
                barrier();
                uint64_t t0=ns(CLOCK_MONOTONIC_RAW);
                sink^=p[0];
                barrier();
                uint64_t dt=ns(CLOCK_MONOTONIC_RAW)-t0;
                samples[count++]=dt;
            }
            if (count) {
                qsort(samples,count,sizeof(samples[0]),compare);
                printf("slot=%d offset_expected=%d n=%d median_ns=%llu p25=%llu p75=%llu\n",
                  slot,slot%2?4096:0,count,
                  (unsigned long long)samples[count/2],
                  (unsigned long long)samples[count/4],
                  (unsigned long long)samples[3*count/4]);
                fflush(stdout);
            }
        }
    }
    munmap((void*)p,8192);
    free(evict);
    return 0;
}
