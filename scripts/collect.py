import csv, glob, os, re, sys
from collections import defaultdict

TLP = "/root/gem5/tlp"
RES = os.path.join(TLP, "results")

# op classes executed by MinorDefaultFloatSimdFU (copied from BaseMinorCPU.py)
FSIMD = set("""FloatAdd FloatCmp FloatCvt FloatMisc FloatMult FloatMultAcc FloatDiv
FloatSqrt SimdAdd SimdAddAcc SimdAlu SimdCmp SimdCvt SimdMisc SimdMult SimdMultAcc
SimdMatMultAcc SimdShift SimdShiftAcc SimdDiv SimdSqrt SimdFloatAdd SimdFloatAlu
SimdFloatCmp SimdFloatCvt SimdFloatDiv SimdFloatMisc SimdFloatMult SimdFloatMultAcc
SimdFloatMatMultAcc SimdFloatSqrt SimdReduceAdd SimdReduceAlu SimdReduceCmp
SimdFloatReduceAdd SimdFloatReduceCmp SimdAes SimdAesMix SimdSha1Hash SimdSha1Hash2
SimdSha256Hash SimdSha256Hash2 SimdShaSigma2 SimdShaSigma3 Matrix MatrixMov MatrixOP
SimdExt SimdFloatExt SimdConfig""".split())

DIR_RE = re.compile(r"N(\d+)_op(\d+)_is(\d+)_t(\d+)$")
CPU_RE = re.compile(r"^system\.cpu(\d*)\.(.+)$")


def read_dumps(path):
    dumps, cur = [], None
    with open(path) as f:
        for line in f:
            if "Begin Simulation Statistics" in line:
                cur = {}
            elif "End Simulation Statistics" in line:
                dumps.append(cur); cur = None
            elif cur is not None:
                p = line.split()
                if len(p) >= 2:
                    try:
                        cur[p[0]] = float(p[1])
                    except ValueError:
                        pass
    return dumps


def read_threads(d):
    thr, ok = {}, None
    for fn in glob.glob(os.path.join(d, "simout*")):
        for line in open(fn, errors="replace"):
            if line.startswith("DAXPY"):
                ok = "PASS" in line
            m = re.match(r"THREAD (\d+) start_wait=(\d+) compute=(\d+) end_wait=(\d+) total=(\d+)", line)
            if m:
                thr[int(m.group(1))] = dict(start_wait=int(m.group(2)), compute=int(m.group(3)),
                                            end_wait=int(m.group(4)), total=int(m.group(5)))
    return thr, ok


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


runs, threads = [], []
for d in sorted(glob.glob(os.path.join(RES, "runs", "*"))):
    m = DIR_RE.search(d)
    st = os.path.join(d, "stats.txt")
    if not m or not os.path.exists(st):
        continue
    N, op, iss, T = map(int, m.groups())
    dumps = read_dumps(st)
    thr, ok = read_threads(d)
    if len(dumps) < 2:
        print("WARNING: %s has %d stat dumps (need >=2) - skipped" % (d, len(dumps)))
        continue
    roi = dumps[1]
    period = roi.get("system.clk_domain.clock", 1000.0)          # ticks per cycle
    roi_ticks = roi.get("simTicks", 0.0)

    cores = defaultdict(dict)
    for k, v in roi.items():
        cm = CPU_RE.match(k)
        if cm:
            cores[int(cm.group(1) or 0)][cm.group(2)] = v

    rows = []
    for c in sorted(cores):
        s = cores[c]
        cyc = s.get("numCycles", 0.0)
        insts = s.get("commitStats0.numInsts", s.get("committedInsts", 0.0))
        q = s.get("quiesceCycles", 0.0)
        fs = sum(v for k, v in s.items()
                 if k.startswith("commitStats0.committedInstType::")
                 and k.split("::")[1] in FSIMD)
        t = thr.get(c, {})
        rows.append(dict(
            N=N, T=T, opLat=op, issueLat=iss, core=c,
            cycles=int(cyc), insts=int(insts),
            ipc=insts / cyc if cyc else 0, cpi=cyc / insts if insts else 0,
            quiesce_cycles=int(q),
            active_ipc=insts / (cyc - q) if cyc - q > 0 else 0,
            fsimd_ops=int(fs),
            fsimd_per_cycle=fs / cyc if cyc else 0,
            fu_util=fs * iss / cyc if cyc else 0,      # fraction of cycles the FU cannot accept a new op
            l1d_miss_rate=s.get("dcache.overallMissRate::total"),
            compute_cyc=t.get("compute"), start_wait=t.get("start_wait"),
            end_wait=t.get("end_wait"), thread_total=t.get("total")))
    threads += rows

    sync = mean([(r["start_wait"] + r["end_wait"]) / r["thread_total"]
                 for r in rows if r["thread_total"]])
    imb = None
    comp = [r["compute_cyc"] for r in rows if r["compute_cyc"]]
    if comp:
        imb = max(comp) / mean(comp)
    host = os.path.join(d, "host_seconds.txt")
    runs.append(dict(
        N=N, T=T, opLat=op, issueLat=iss, design="%d/%d" % (op, iss),
        passed=ok, roi_ticks=int(roi_ticks), roi_us=roi_ticks / 1e6,
        roi_cycles=int(roi_ticks / period),
        total_insts=sum(r["insts"] for r in rows),
        avg_ipc=mean([r["ipc"] for r in rows]), avg_cpi=mean([r["cpi"] for r in rows]),
        avg_active_ipc=mean([r["active_ipc"] for r in rows]),
        system_ipc=sum(r["insts"] for r in rows) / (roi_ticks / period) if roi_ticks else 0,
        fsimd_ops=sum(r["fsimd_ops"] for r in rows),
        avg_fu_util=mean([r["fu_util"] for r in rows]),
        sync_overhead=sync, load_imbalance=imb,
        l1d_miss_rate=mean([r["l1d_miss_rate"] for r in rows]),
        l2_misses=roi.get("system.l2cache.overallMisses::total"),
        host_seconds=open(host).read().strip() if os.path.exists(host) else ""))

if not runs:
    sys.exit("no finished runs found under %s/runs" % RES)

base = {(r["N"], r["opLat"]): r["roi_ticks"] for r in runs if r["T"] == 1}
for r in runs:
    b = base.get((r["N"], r["opLat"]))
    r["speedup"] = b / r["roi_ticks"] if b and r["roi_ticks"] else None
    r["efficiency"] = r["speedup"] / r["T"] if r["speedup"] else None
runs.sort(key=lambda r: (r["N"], r["T"], r["opLat"]))
threads.sort(key=lambda r: (r["N"], r["T"], r["opLat"], r["core"]))


def write_csv(fn, rows):
    with open(fn, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


write_csv(os.path.join(RES, "runs.csv"), runs)
write_csv(os.path.join(RES, "per_thread.csv"), threads)

def fmt(v, f):
    return "-" if v is None else f % v


METRICS = [("roi_us", "ROI time (us)", "%.2f"),
           ("speedup", "Parallel speedup vs 1 thread (same design)", "%.2f"),
           ("efficiency", "Parallel efficiency (speedup/T)", "%.2f"),
           ("avg_ipc", "Average IPC per thread (core)", "%.3f"),
           ("avg_cpi", "Average CPI per thread (core)", "%.3f"),
           ("avg_active_ipc", "Average IPC per thread, excluding quiesced (blocked) cycles", "%.3f"),
           ("avg_fu_util", "FloatSimdFU utilization (fsimd ops x issueLat / cycles)", "%.3f"),
           ("sync_overhead", "Sync overhead (barrier wait / thread ROI time)", "%.3f"),
           ("load_imbalance", "Load imbalance (max/mean compute cycles)", "%.3f"),
           ("l1d_miss_rate", "Average L1D miss rate", "%.4f")]

idx = {(r["N"], r["T"], r["opLat"]): r for r in runs}
Ns = sorted({r["N"] for r in runs}); Ts = sorted({r["T"] for r in runs})
ops = sorted({r["opLat"] for r in runs})
out = ["# FloatSimdFU design sweep (opLat + issueLat = 7)\n",
       "Design column = opLat/issueLat. Default MinorCPU design is 6/1.\n"]
for N in Ns:
    out.append("\n## N = %d\n" % N)
    for key, title, f in METRICS:
        out.append("\n**%s**\n\n| design | " % title + " | ".join("T=%d" % t for t in Ts) + " |")
        out.append("|---|" + "---|" * len(Ts))
        for op in ops:
            cells = [fmt(idx[(N, t, op)][key], f) if (N, t, op) in idx else "-" for t in Ts]
            out.append("| %d/%d | " % (op, 7 - op) + " | ".join(cells) + " |")
    out.append("\n**Best design per thread count**\n\n| T | fastest (min ROI time) | ROI us | best speedup | speedup |")
    out.append("|---|---|---|---|---|")
    for t in Ts:
        rs = [idx[(N, t, op)] for op in ops if (N, t, op) in idx]
        if not rs:
            continue
        fast = min(rs, key=lambda r: r["roi_ticks"])
        sp = [r for r in rs if r["speedup"]]
        bsp = max(sp, key=lambda r: r["speedup"]) if sp else None
        out.append("| %d | %s | %.2f | %s | %s |" % (t, fast["design"], fast["roi_us"],
                   bsp["design"] if bsp else "-", fmt(bsp["speedup"] if bsp else None, "%.2f")))
bad = [r for r in runs if not r["passed"]]
out.append("\nRuns not PASS: %s\n" % (", ".join("N%d op%d t%d" % (r["N"], r["opLat"], r["T"]) for r in bad) or "none"))
open(os.path.join(RES, "tables.md"), "w").write("\n".join(out) + "\n")
print("wrote %d runs -> results/runs.csv, per_thread.csv, tables.md" % len(runs))
