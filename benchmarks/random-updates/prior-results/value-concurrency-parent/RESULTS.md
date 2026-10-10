# Current value-bank concurrency outcomes

Exact672 records verified; full state/recovered receipt frontier, group histograms, O_DSYNC counters and maintenance accounting passed. Both campaigns completed.

- 100000 rows/1 clients: service 3.2864x / 4.5893x; setup-inclusive 3.2518x / 4.5389x.
- 100000 rows/4 clients: service 3.0681x / 4.4652x; setup-inclusive 3.0225x / 4.4080x.
- 100000 rows/16 clients: service 3.2644x / 4.4206x; setup-inclusive 3.1827x / 4.4429x.
- 100000 rows/64 clients: service 2.3743x / 4.8308x; setup-inclusive 2.2975x / 4.5272x.
- 1000000 rows/1 clients: service 6.2552x / 2.2013x; setup-inclusive 5.8845x / 2.1752x.
- 1000000 rows/4 clients: service 5.4333x / 1.7173x; setup-inclusive 5.0166x / 1.7372x.
- 1000000 rows/16 clients: service 4.2902x / 2.1493x; setup-inclusive 3.7048x / 2.0912x.
- 1000000 rows/64 clients: service 3.1708x / 2.3863x; setup-inclusive 2.8028x / 2.3212x.

Gate FAIL: 1M/4client campaign2 service1.7173x,cold1.7372x. 1M/64client p99 loses both campaigns (native26.94/27.27ms versus bestSQLite16.49/9.15ms). Other14/16 campaign cells pass p99. No claim of universal2x or new engine breakthrough; unchanged singleton comparator varied substantially.

Failed4client phase budget: sync86.31%,checkpoint7.22%. Hypothetically removing ALL checkpoints only reaches1.8509x; checkpoint tuning alone cannot close this observed service gap.

Next bounded sustained qualification uses unchanged source/geometry for failed4client and tail-sensitive64client cells,131072requests (4x horizon),100k/1Mrows,both caches/fiveWALthresholds,two campaigns/three repeats,336records. Separates sustained evidence from the short campaign; no artificial batching or weaker ack. No physicalpowerloss/generalCRUD claim, no production edits. Raw records only exported to avoid duplicating fixture databases. Prior blocked destructive cleanup was not retried.
