import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = "/root/gem5/tlp/results"
OUT = os.path.join(RES, "plots"); os.makedirs(OUT, exist_ok=True)


def load(fn):
    rows = list(csv.DictReader(open(os.path.join(RES, fn))))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v)
            except (ValueError, TypeError):
                pass
    return rows


runs, thr = load("runs.csv"), load("per_thread.csv")
Ns = sorted({int(r["N"]) for r in runs}); Ts = sorted({int(r["T"]) for r in runs})
ops = sorted({int(r["opLat"]) for r in runs})
labels = ["%d/%d" % (o, 7 - o) for o in ops]


def get(N, T, op, key):
    for r in runs:
        if r["N"] == N and r["T"] == T and r["opLat"] == op:
            return r[key] if isinstance(r[key], float) else None
    return None


PLOTS = [("roi_us", "ROI time (us)", True, None),
         ("speedup", "Parallel speedup vs 1 thread", False, 2),
         ("avg_ipc", "Average IPC per thread", False, None),
         ("avg_fu_util", "FloatSimdFU utilization", False, None),
         ("sync_overhead", "Sync overhead fraction", False, 2)]

for N in Ns:
    for key, ylab, logy, tmin in PLOTS:
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for T in Ts:
            if tmin and T < tmin:
                continue
            ys = [get(N, T, o, key) for o in ops]
            ax.plot(labels, ys, marker="o", label="T=%d" % T)
        if key == "speedup":
            for T in Ts:
                if T >= 2:
                    ax.axhline(T, ls=":", lw=0.8, color="gray")
        ax.set_xlabel("FloatSimdFU design (opLat / issueLat)")
        ax.set_ylabel(ylab)
        if logy:
            ax.set_yscale("log")
        ax.set_title("%s, N=%d" % (ylab, N))
        ax.grid(alpha=0.3); ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "%s_N%d.png" % (key, N)), dpi=150)
        plt.close(fig)

    # per-thread IPC for the largest thread count
    T = max(Ts)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    w = 0.8 / T
    for c in range(T):
        ys = []
        for o in ops:
            v = [r["ipc"] for r in thr if r["N"] == N and r["T"] == T and r["opLat"] == o and r["core"] == c]
            ys.append(v[0] if v else 0)
        ax.bar([i + c * w for i in range(len(ops))], ys, w, label="core %d" % c)
    ax.set_xticks([i + 0.4 - w / 2 for i in range(len(ops))]); ax.set_xticklabels(labels)
    ax.set_xlabel("FloatSimdFU design (opLat / issueLat)"); ax.set_ylabel("IPC")
    ax.set_title("Per-thread IPC, T=%d, N=%d" % (T, N)); ax.legend(fontsize=7, ncol=4)
    ax.grid(alpha=0.3, axis="y"); fig.tight_layout()
    fig.savefig(os.path.join(OUT, "per_thread_ipc_T%d_N%d.png" % (T, N)), dpi=150)
    plt.close(fig)

print("plots in", OUT)
