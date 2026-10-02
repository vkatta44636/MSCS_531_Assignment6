# tlp_config.py - N-core MinorCPU (in-order) shared-memory system, SE mode.
import argparse
import m5
import m5.objects as mobj
from m5.objects import *
from m5.SimObject import SimObject


def sim_class(*names):
    """Return the first name that is a SimObject class (v24 naming quirks)."""
    for n in names:
        c = getattr(mobj, n, None)
        if isinstance(c, type) and issubclass(c, SimObject):
            return c
    raise RuntimeError("no SimObject class found for any of: %s" % (names,))


ap = argparse.ArgumentParser()
ap.add_argument("--cmd", required=True, help="x86 static binary")
ap.add_argument("--options", default="", help="program arguments")
ap.add_argument("--cpus", type=int, default=1, help="number of cores")
ap.add_argument("--oplat", type=int, default=6, help="FloatSimdFU opLat")
ap.add_argument("--issuelat", type=int, default=1, help="FloatSimdFU issueLat")
ap.add_argument("--clock", default="1GHz")
ap.add_argument("--l2size", default="2MB")
args = ap.parse_args()

CPU = sim_class("X86MinorCPU", "MinorCPU", "BaseMinorCPU")
FloatSimdFU = sim_class("MinorDefaultFloatSimdFU")
ProcessCls = sim_class("Process")

system = System()
system.clk_domain = SrcClockDomain(clock=args.clock,
                                   voltage_domain=VoltageDomain())
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("1GB")]

system.cpu = [CPU(cpu_id=i) for i in range(args.cpus)]

system.membus = SystemXBar()
system.l2bus = L2XBar()
system.l2cache = Cache(size=args.l2size, assoc=8, tag_latency=10,
                       data_latency=10, response_latency=10,
                       mshrs=32, tgts_per_mshr=12)
system.l2cache.cpu_side = system.l2bus.mem_side_ports
system.l2cache.mem_side = system.membus.cpu_side_ports


def l1(size):
    return Cache(size=size, assoc=2, tag_latency=2, data_latency=2,
                 response_latency=2, mshrs=4, tgts_per_mshr=20)


fu_report = []
for cpu in system.cpu:
    # ---- FloatSimdFU design point (opLat + issueLat) ----
    for idx, fu in enumerate(cpu.executeFuncUnits.funcUnits):
        if isinstance(fu, FloatSimdFU):
            fu.opLat = args.oplat
            fu.issueLat = args.issuelat
            fu_report.append(idx)

    cpu.icache = l1("32kB")
    cpu.dcache = l1("32kB")
    cpu.icache_port = cpu.icache.cpu_side
    cpu.dcache_port = cpu.dcache.cpu_side
    cpu.icache.mem_side = system.l2bus.cpu_side_ports
    cpu.dcache.mem_side = system.l2bus.cpu_side_ports
    cpu.mmu.connectWalkerPorts(system.l2bus.cpu_side_ports,
                               system.l2bus.cpu_side_ports)

    cpu.createInterruptController()
    cpu.interrupts[0].pio = system.membus.mem_side_ports
    cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
    cpu.interrupts[0].int_responder = system.membus.mem_side_ports

if len(fu_report) != args.cpus:
    raise RuntimeError("FloatSimd FU not found in every core's FU pool")

system.system_port = system.membus.cpu_side_ports
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8(range=system.mem_ranges[0])
system.mem_ctrl.port = system.membus.mem_side_ports

# one process; every core gets it, only core 0 starts - pthread_create
# (clone/clone3 syscall) activates the next free core's thread context
system.workload = SEWorkload.init_compatible(args.cmd)
proc = ProcessCls(pid=100)
proc.cmd = [args.cmd] + args.options.split()
for cpu in system.cpu:
    cpu.workload = proc
    cpu.createThreads()

print("TLP config: cores=%d  FloatSimdFU(funcUnits[%d]) opLat=%d issueLat=%d"
      % (args.cpus, fu_report[0], args.oplat, args.issuelat))

root = Root(full_system=False, system=system)
m5.instantiate()
ev = m5.simulate()
print("Exiting @ tick %i because %s" % (m5.curTick(), ev.getCause()))
