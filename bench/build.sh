set -e
cd "$(dirname "$0")"
mkdir -p ../results/asm
CC=x86_64-linux-gnu-gcc
$CC -O2 -fno-tree-vectorize -static -no-pie -pthread -o daxpy_mt daxpy_mt.c -lm
file daxpy_mt

if command -v qemu-x86_64 >/dev/null; then
    echo "== QEMU sanity check (m5ops skipped) =="
    for T in 1 2 4 8; do qemu-x86_64 ./daxpy_mt 4096 $T nom5 | head -1; done \
        | tee ../results/asm/qemu_check.txt
fi

x86_64-linux-gnu-objdump -d --no-show-raw-insn daxpy_mt \
    | awk '/<daxpy>:/,/^$/' | tee ../results/asm/daxpy_kernel.txt
