# Builds Shell_x_tests.png from the traces and test_log.txt.
import csv, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

def load(name):
    rows = list(csv.DictReader(open(f"traces/{name}.csv")))
    ev = list(csv.DictReader(open(f"traces/{name}_events.csv")))
    t = [float(r["t_ms"]) for r in rows]; z = [float(r["z_mm"]) for r in rows]
    sg = [int(r["sg"]) for r in rows]; d = [int(r["diag"]) for r in rows]
    return t, z, sg, d, [(float(e["t_ms"]), e["line"]) for e in ev]

log = open("test_log.txt").read()
tests = re.findall(r"^\[(PASS|FAIL)\] (\S+)", log, re.M)
total = re.search(r"RESULT (\d+)/(\d+)", log)

fig = plt.figure(figsize=(20, 15), facecolor="#0f172a")
fig.suptitle(f"Shell x host tests: {total.group(1)}/{total.group(2)} passed (real Shell_x.ino + simulated TMC2209 and Z axis)",
             color="white", fontsize=22, fontweight="bold", y=0.985)
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.05], hspace=0.28, wspace=0.18, left=0.05, right=0.97, top=0.93, bottom=0.03)

def panel(ax, name, title, floor, sponge, xlim=None):
    t, z, sg, d, ev = load(name)
    ax.set_facecolor("#f8fafc")
    ax.plot(t, z, color="#7c3aed", lw=2.5, label="Z height (mm)")
    ax.axhline(floor, color="#334155", ls="--", lw=1.5); ax.text(t[0] + 5, floor + 0.4, "object top", color="#334155", fontsize=11)
    if sponge:
        ax.axhspan(floor - 5, floor, color="#fde68a", alpha=0.6); ax.text(t[0] + 5, floor - 2.8, "5 mm sponge", color="#92400e", fontsize=11)
    ax.set_ylabel("Z height (mm)", color="#7c3aed", fontsize=13); ax.set_xlabel("time (ms)", fontsize=12)
    ax2 = ax.twinx()
    ax2.plot(t, sg, color="#ea580c", lw=1.4, alpha=0.9, label="SG_RESULT")
    ax2.fill_between(t, 0, [x * 25 for x in d], color="#dc2626", alpha=0.25, step="pre", label="DIAG high")
    ax2.set_ylim(0, 520); ax2.set_ylabel("SG_RESULT (0-510)", color="#ea580c", fontsize=13)
    ax2.axhline(140, color="#dc2626", ls=":", lw=1.5); ax2.text(t[-1] * 0.995, 146, "2 x SGTHRS = 140 (DIAG)", color="#dc2626", ha="right", fontsize=10)
    colors = {"ZG": "#0284c7", "ZP": "#0284c7", "ZS": "#16a34a", "SG": "#dc2626", "ZB": "#0d9488", "Z0": "#be185d"}
    y = 470
    for tm, line in ev:
        key = line[:2]
        if key not in colors or line.startswith("SG:") and not line.startswith("SG:HIT"): continue
        ax2.axvline(tm, color=colors[key], lw=2, alpha=0.8)
        ax2.text(tm + 4, y, line, color=colors[key], fontsize=11, fontweight="bold", rotation=0,
                 bbox=dict(facecolor="white", edgecolor=colors[key], alpha=0.85, boxstyle="round,pad=0.2"))
        y -= 38
        if y < 260: y = 470
    ax2.axvspan(t[0], t[0] + 0, color="none")
    ax.set_title(title, fontsize=16, fontweight="bold", color="white", backgroundcolor="#1e293b", pad=10)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower left", fontsize=11)
    if xlim: ax.set_xlim(*xlim)
    return t, sg, ev

panel(fig.add_subplot(gs[0, 0]), "zg", "ZG pickup on a hard object, then G45, then ZR back to Z0", -10, False)
t, sg, ev = panel(fig.add_subplot(gs[0, 1]), "zp", "ZP press into a sponge: baseline, SG threshold, 0.5 mm back-off, ZR", -12, True)
# baseline / threshold from SG:HIT line
hit = [l for _, l in ev if l.startswith("SG:HIT")]
if hit:
    base = int(re.search(r"BASE=(\d+)", hit[0]).group(1))
    ax2 = fig.axes[-1]
    ax2.axhline(base, color="#16a34a", ls="--", lw=1.5); ax2.text(t[0] + 5, base + 6, f"baseline {base}", color="#16a34a", fontsize=11)
    ax2.axhline(base - 80, color="#b45309", ls="--", lw=1.5); ax2.text(t[0] + 5, base - 74, f"press threshold {base - 80} (baseline - 80)", color="#b45309", fontsize=11)

ax = fig.add_subplot(gs[1, :]); ax.axis("off"); ax.set_facecolor("#0f172a")
ax.set_title("Pass / fail table", fontsize=17, fontweight="bold", color="white", backgroundcolor="#1e293b", pad=8)
cols = 3; per = (len(tests) + cols - 1) // cols
palette = ["#38bdf8", "#a78bfa", "#f472b6", "#fb923c", "#2dd4bf", "#facc15"]
for i, (res, name) in enumerate(tests):
    c, r = divmod(i, per)
    x = 0.005 + c * 0.333; y = 0.95 - r * (0.93 / per)
    ok = res == "PASS"
    ax.add_patch(FancyBboxPatch((x, y - 0.075), 0.32, 0.068, boxstyle="round,pad=0.004", transform=ax.transAxes,
                                facecolor=palette[i % len(palette)], edgecolor="#0f172a", alpha=0.95))
    ax.add_patch(FancyBboxPatch((x + 0.005, y - 0.067), 0.05, 0.052, boxstyle="round,pad=0.003", transform=ax.transAxes,
                                facecolor="#16a34a" if ok else "#dc2626", edgecolor="white"))
    ax.text(x + 0.03, y - 0.041, res, transform=ax.transAxes, ha="center", va="center", color="white", fontsize=12, fontweight="bold")
    ax.text(x + 0.062, y - 0.041, f"{i + 1:02d}  {name.replace('_', ' ')}", transform=ax.transAxes, va="center", color="#0f172a", fontsize=12.5, fontweight="bold")
fig.savefig("Shell_x_tests.png", dpi=90, facecolor=fig.get_facecolor())
print("saved")
