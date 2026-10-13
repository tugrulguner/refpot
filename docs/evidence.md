# Historical benchmark evidence

**This is historical prototype evidence, not a benchmark of the published Python package.** RefPot's current package performance remains unqualified. The experimental alpha has CRUD and transactions; the measured prototype below used a different fixed-schema update path. Do not transfer its ratios or storage guarantees to the package.

## Read the chart correctly

Service and setup-inclusive ratios compare best-tested SQLite time with native prototype time under the experiment's matched policy. A ratio above one favors the prototype. The two campaigns are retained separately; the 2× line is the scoped acceptance threshold, not a universal database guarantee. The chart's reopen failure includes a full-state oracle scan, not isolated recovery latency.

All 16 service/setup/p99 cells passed in this experiment, but reopen and full-state validation lost every cell. Read the full per-cell values and fairness contract below before citing a ratio. Earlier failed experiments are retained rather than discarded. Linux ARM64 Docker/ext4 VM measurements do not establish native macOS, Linux x86_64, bare-metal, Python-binding, ORM, or physical power-loss performance.

## Evidence index

- [Frozen experimental source and original report](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates)
- [Independent read-only audit](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/AUDIT.md)
- [Raw records archive](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/data/raw-records.tar.gz)
- [Source and evidence hash manifest](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/manifest.json)
- [Complete analyzer output](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/summary.json)
- [All reopen comparisons](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/recovery-comparison.json)
- [Prior failed experiments](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates/prior-results)
- [Reproduction tool](https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/reproduce.py)

## Verify evidence versus rerunning measurements

From a repository checkout, the offline `verify` command below checks the retained hashes, recomputes all 672 raw records and validates the declared matrix. It does **not** execute a new performance campaign or qualify the public package.

The Docker `smoke` command executes actual native and SQLite operations with reopen checks, but its timings are not a complete comparison. The full `campaign` is an explicit expensive opt-in, around ten hours on the recorded machine; it downloads SQLite and uses Docker. Do not run it automatically as part of trying the package. New measurements with a mutable toolchain image are a new experiment, not an exact replay of the old environment.

For future package measurements, use the [performance qualification method](/performance-method/). For actual supported operations and failure boundaries, read the [package contract](/package-contract/) and [errors and ownership guide](/build/errors/).
