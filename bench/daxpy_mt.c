/*
 * daxpy_mt.c - multi-threaded DAXPY (Y = alpha*X + Y) for gem5 SE mode.
 *
 * Usage:  daxpy_mt N T [nom5]
 *   N    vector length                 T  number of threads (= gem5 cores)
 *   nom5 skip the m5ops (for a native/QEMU sanity run only)
 *
 * The annotated region of the provided single-threaded kernel
 *      m5_dump_reset_stats(0, 0);
 *      for (i...) Y[i] = alpha * X[i] + Y[i];
 *      m5_dump_reset_stats(0, 0);
 * is kept, but the loop is split into T contiguous chunks, one per thread.
 * The main thread is thread 0, so T threads need exactly T cores.
 * Barriers make every thread start the kernel together; thread 0 issues the
 * two stat dumps, so stats dump #2 in stats.txt = the parallel kernel (ROI).
 *
 * Per thread, rdtsc (= that core's cycle count in gem5) records:
 *   compute  = cycles spent in its own daxpy chunk
 *   wait     = cycles blocked in the start + end barriers (sync overhead)
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <x86intrin.h>
#include "m5_inline.h"

#define MAXT 64
#define LINE_DBL 8                      /* 8 doubles = one 64-byte line */

typedef struct {
    uint64_t ta, t0, t1, t2;   /* before start barrier, kernel start, kernel end, after end barrier */
    char pad[64 - 4 * sizeof(uint64_t)];
} __attribute__((aligned(64))) rec_t;

static double *X, *Y;
static const double alpha = 0.5;
static long N;
static int T, use_m5 = 1;
static pthread_barrier_t bar;
static rec_t rec[MAXT];

__attribute__((noinline))
static void daxpy(long lo, long hi) {
    for (long i = lo; i < hi; ++i)
        Y[i] = alpha * X[i] + Y[i];
}

static void *worker(void *arg) {
    int tid = (int)(intptr_t)arg;
    long chunk = (N + T - 1) / T;
    chunk = (chunk + LINE_DBL - 1) / LINE_DBL * LINE_DBL;   /* no false sharing at chunk edges */
    long lo = (long)tid * chunk;
    if (lo > N) lo = N;
    long hi = lo + chunk < N ? lo + chunk : N;

    pthread_barrier_wait(&bar);                          /* all threads exist */
    if (tid == 0 && use_m5) m5_dump_reset_stats(0, 0);   /* ---- Start of daxpy loop (ROI) ---- */
    rec[tid].ta = __rdtsc();
    pthread_barrier_wait(&bar);                          /* everyone starts together */
    rec[tid].t0 = __rdtsc();
    daxpy(lo, hi);
    rec[tid].t1 = __rdtsc();
    pthread_barrier_wait(&bar);                          /* wait for the slowest thread */
    rec[tid].t2 = __rdtsc();
    if (tid == 0 && use_m5) m5_dump_reset_stats(0, 0);   /* ---- End of daxpy loop (ROI) ---- */
    return NULL;
}

int main(int argc, char **argv) {
    N = argc > 1 ? atol(argv[1]) : 4096;
    T = argc > 2 ? atoi(argv[2]) : 1;
    if (argc > 3 && strcmp(argv[3], "nom5") == 0) use_m5 = 0;
    if (T < 1 || T > MAXT || N < 1) { fprintf(stderr, "bad args\n"); return 1; }

    size_t bytes = ((N * sizeof(double) + 63) / 64) * 64;
    X = aligned_alloc(64, bytes);
    Y = aligned_alloc(64, bytes);
    double *Y0 = malloc(N * sizeof(double));
    /* inputs in [1,2) like the provided kernel, from a deterministic LCG
       (std::random_device is avoided: not dependable in gem5 SE mode) */
    uint64_t s = 12345;
    for (long i = 0; i < N; ++i) {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        X[i] = 1.0 + (double)(s >> 11) / 9007199254740992.0;
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        Y[i] = 1.0 + (double)(s >> 11) / 9007199254740992.0;
        Y0[i] = Y[i];
    }

    pthread_barrier_init(&bar, NULL, T);
    pthread_t th[MAXT];
    for (int t = 1; t < T; ++t)
        if (pthread_create(&th[t], NULL, worker, (void *)(intptr_t)t)) { perror("pthread_create"); return 1; }
    worker((void *)0);                                   /* main thread = thread 0 */
    for (int t = 1; t < T; ++t) pthread_join(th[t], NULL);

    /* verification + output (outside the ROI) */
    double sum = 0, maxerr = 0;
    for (long i = 0; i < N; ++i) {
        double e = fabs(Y[i] - (alpha * X[i] + Y0[i]));
        if (e > maxerr) maxerr = e;
        sum += Y[i];
    }
    printf("DAXPY N=%ld T=%d sum=%.6f maxerr=%g %s\n", N, T, sum, maxerr,
           maxerr < 1e-12 ? "PASS" : "FAIL");
    for (int t = 0; t < T; ++t)
        printf("THREAD %d start_wait=%llu compute=%llu end_wait=%llu total=%llu\n", t,
               (unsigned long long)(rec[t].t0 - rec[t].ta),
               (unsigned long long)(rec[t].t1 - rec[t].t0),
               (unsigned long long)(rec[t].t2 - rec[t].t1),
               (unsigned long long)(rec[t].t2 - rec[t].ta));
    return 0;
}
