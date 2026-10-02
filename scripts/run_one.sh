N=$1; T=$2; OP=$3; IS=$4
TLP=/root/gem5/tlp
GEM5BIN=${GEM5BIN:-/root/gem5/build/X86/gem5.opt}
OUT=$TLP/results/runs/N${N}_op${OP}_is${IS}_t${T}
mkdir -p "$OUT"
start=$(date +%s)
"$GEM5BIN" -re --outdir="$OUT" "$TLP/configs/tlp_config.py" \
    --cmd="$TLP/bench/daxpy_mt" --options="$N $T" \
    --cpus="$T" --oplat="$OP" --issuelat="$IS" > /dev/null 2>&1
rc=$?
echo "$(( $(date +%s) - start ))" > "$OUT/host_seconds.txt"
status=$(grep -ho "PASS\|FAIL" "$OUT"/simout* 2>/dev/null | head -1)
printf "N=%-7s T=%s opLat=%s issueLat=%s rc=%s %s\n" "$N" "$T" "$OP" "$IS" "$rc" "${status:-NO-OUTPUT}"
