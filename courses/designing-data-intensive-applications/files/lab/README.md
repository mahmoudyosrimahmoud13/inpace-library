# Data-intensive systems lab

Small, runnable implementations of the big ideas in *Designing Data-Intensive Applications* by Martin Kleppmann.
Plain Python 3.9+, standard library only: nothing to install. Each script prints what it demonstrates.
Generated files go to `lab_data/` (safe to delete; keep it out of git).

| Day | Script | What you build |
|---|---|---|
| 1 | `p01_load_and_latency.py` | Twitter's timeline fan-out; percentiles and tail latency amplification |
| 2 | `p02_data_models.py` | Relational, document and graph models; a recursive graph query; schema on read vs write |
| 3 | `p03_logkv.py` | A Bitcask-style log-structured store: hash index, segments, compaction, crash recovery |
| 4 | `p04_lsm.py` | An LSM-tree: WAL, memtable, SSTables, sparse index, Bloom filters, compaction |
| 5 | `p05_columns.py` | Row vs column storage, bitmaps, run-length encoding, a data cube |
| 6 | `p06_encoding.py` | Protocol Buffers- and Avro-style encodings, schema evolution |
| 7 | `p07_replication.py` | Leader-follower lag anomalies, failover data loss, leaderless quorums |
| 8 | `p08_partitioning.py` | Range vs hash partitioning, rebalancing, secondary indexes, hot keys |
| 9 | `p09_transactions.py` | MVCC with read committed, snapshot isolation and serializable (SSI) |
| 10 | `p10_faults.py` | Timeouts, clock skew losing writes, leases and fencing tokens |
| 11 | `p11_consensus.py` | Linearizability, Lamport timestamps, two-phase commit, leader election |
| 12 | `p12_mapreduce.py` | MapReduce with parallel processes; sort-merge and broadcast joins |
| 13 | `p13_streams.py` | A partitioned log with offsets; dual writes vs CDC; a stream-table join |
| 14 | `p14_unbundled.py` | An unbundled database: one event log, derived views, request IDs, audits |
