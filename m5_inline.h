/* m5_inline.h - gem5 "magic instruction" m5ops for x86, as inline asm.
 * Same encoding as gem5's util/m5/src/abi/x86/m5op.S (0x0F 0x04 <func16>),
 * so there is no need to cross-build libm5.a. Args in rdi/rsi like the real ABI.
 *   0x40 reset_stats   0x41 dump_stats   0x42 dump_reset_stats
 * NOTE: this opcode is illegal on a real CPU (SIGILL) - only run under gem5,
 * or pass "nom5" to daxpy_mt to skip it.                                    */
#ifndef M5_INLINE_H
#define M5_INLINE_H
#include <stdint.h>
static inline void m5_dump_reset_stats(uint64_t delay, uint64_t period) {
    __asm__ volatile(".byte 0x0f, 0x04\n\t.word 0x42"
                     : : "D"(delay), "S"(period) : "rax", "memory");
}
#endif
