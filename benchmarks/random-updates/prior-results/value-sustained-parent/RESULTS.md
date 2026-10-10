# Sustained qualification outcomes

Exact336records verified;131072requests/trial,both campaigns,fulltuple/frontier recovery and synchronizedwrite/group/checkpoint assertions passed.

- 100000rows/4clients: service 2.897974x / 4.516429x; setup-inclusive 2.888001x / 4.464413x.
- 100000rows/64clients: service 2.316491x / 2.704303x; setup-inclusive 2.288698x / 2.672121x.
- 1000000rows/4clients: service 4.086352x / 1.927933x; setup-inclusive 4.017214x / 1.934808x.
- 1000000rows/64clients: service 2.754496x / 1.900671x; setup-inclusive 2.740567x / 1.890114x.

FAIL: both1M campaign2throughput cells miss2x;1M64client p99 losesboth campaigns. Longer duration did not remove failures.100k cells passboth metricsboth campaigns.

4clients: checkpoint7.01%,sync84.87%;nativep990.469ms,bestSQL11.823ms,checkpoints32.0.

64clients: checkpoint41.83%,sync34.36%;nativep9925.747ms,bestSQL18.010ms,checkpoints33.0.

Next experiment: fixed1Mrows131072requests4/64clients,redo slot horizon current vs4x;unchanged sync/ack/valuebankprotocol. This isolates persisted ring capacity,charging allsetup/finalmaintenance,andrequiring>=4checkpoints for every cell. Hypothesis: reducecheckpoint frequency and aggregatecost;64clientstail may improve by reducingthe fractionofrequests blocked oncheckpoints. Not a demonstrated cause or solution. BothSQLcachebudgets/fiveWALthresholds,rotated/reversed order,twofull campaigns/3repeats retained. Sources/raw/reports remain; no destructivecleanup orproduction edits.
