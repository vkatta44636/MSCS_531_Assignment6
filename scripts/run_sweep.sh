TLP=/root/gem5/tlp
SIZES=${SIZES:-"4096 65536 262144"}
THREADS=${THREADS:-"1 2 4 8"}
JOBS=${JOBS:-$(nproc)}
SUM=7

mkdir -p $TLP/results
jobs=()
for N in $SIZES; do
  for T in $THREADS; do
    for OP in $(seq 1 $((SUM-1))); do
      echo "$N $T $OP $((SUM-OP))"
    done
  done
done > $TLP/results/joblist.txt

echo "$(wc -l < $TLP/results/joblist.txt) runs, $JOBS in parallel"
cat $TLP/results/joblist.txt | xargs -P "$JOBS" -L 1 $TLP/scripts/run_one.sh \
    | tee $TLP/results/sweep_log.txt
echo "done: $(grep -c PASS $TLP/results/sweep_log.txt) PASS, $(grep -vc PASS $TLP/results/sweep_log.txt) not PASS"
