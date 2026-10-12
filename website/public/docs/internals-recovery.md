## Ownership and concurrency

Only the creating process and creating thread may use or close a database handle; inherited handles cannot be used after `fork()`. Database-path symlinks and hard links are rejected. Parent-directory aliases still refer to the same lock-file inode. Do not delete or replace a held `.lock`, alias the sidecar files, or mutate database files outside the engine. This preview assumes a private, trusted local filesystem namespace.

A process obtains exclusive ownership of a database. The public API is thread-affine; concurrent readers, multiwriter operation, and Windows support are not claimed.


## On-disk behavior

Snapshot files use the `RPSNAP2` version-2 format with sequence and CRC metadata. Each changed-row transaction is represented by two identical checksummed copies in the `.wal` file. Both copies are synchronized before the in-memory state is published. This is redo redundancy in one log, not independent physical replication.

Checkpointing writes and synchronizes a full snapshot, atomically renames it, and synchronizes the parent directory before truncating and synchronizing the log. An incomplete, unacknowledged tail is discarded during recovery; a complete transaction whose two copies are corrupt is rejected. An uncertain write poisons the writer. Recovery is bounded to 64 MiB per snapshot and WAL.

These mechanisms are implementation behavior, not broad recovery qualification. Failure tests and platform review remain in progress; filesystem sync and process tests do not establish physical power-loss safety. No existing-format compatibility is promised.


## Performance and maturity

The historical **3.04–5.95×** result belongs only to the audited experimental update harness, not this Python package. Package performance has not been qualified. The known reopen result remains **16/16 losses** in the historical comparison. Mutation and diff-scan paths copy maps; this is not presented as benchmark-fast, and CPU optimization is future work.

There is no stable API, general performance claim, or production durability guarantee. See the [recommendation](/status/), [roadmap](/project/roadmap/), and [experimental methodology](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates).
