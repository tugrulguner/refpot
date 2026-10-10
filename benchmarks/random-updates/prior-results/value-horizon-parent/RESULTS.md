# Redo horizon outcomes

336 exactrecords verified. Aggregator histogramvariable shadowed horizon token; renamed histogramvariable and reran successfully. Benchmarkrecords unchanged.

Because SQLite engine/config is unchanged across native-horizon tags, choose strongestSQLite across BOTH horizoncontroltags for eachcampaign/client; native6trialmedians remain horizon-specific.
- Campaign1,4clients,horizon1: service3.2374x,cold3.2074x vsstrongestSQLacrossbothunchangedtags; nativep990.550ms,bestSQL8.334ms;checkpointcount32.0.
- Campaign1,4clients,horizon4: service3.5447x,cold3.4957x vsstrongestSQLacrossbothunchangedtags; nativep990.492ms,bestSQL8.334ms;checkpointcount8.0.
- Campaign1,64clients,horizon1: service2.9664x,cold2.9149x vsstrongestSQLacrossbothunchangedtags; nativep9924.450ms,bestSQL10.762ms;checkpointcount33.0.
- Campaign1,64clients,horizon4: service3.4027x,cold3.2704x vsstrongestSQLacrossbothunchangedtags; nativep991.868ms,bestSQL10.762ms;checkpointcount9.0.
- Campaign2,4clients,horizon1: service5.1700x,cold5.0624x vsstrongestSQLacrossbothunchangedtags; nativep990.425ms,bestSQL9.912ms;checkpointcount32.0.
- Campaign2,4clients,horizon4: service5.2947x,cold5.1569x vsstrongestSQLacrossbothunchangedtags; nativep990.464ms,bestSQL9.912ms;checkpointcount8.0.
- Campaign2,64clients,horizon1: service3.4694x,cold3.3484x vsstrongestSQLacrossbothunchangedtags; nativep9925.499ms,bestSQL21.310ms;checkpointcount33.0.
- Campaign2,64clients,horizon4: service3.2760x,cold3.0957x vsstrongestSQLacrossbothunchangedtags; nativep993.436ms,bestSQL21.310ms;checkpointcount9.0.

Allhorizon4 cells passservice/cold2x andp99 inthiscampaignpair,evenagainststrongestunchangedSQLcontrols. 64client p99 drops24.45/25.50ms to1.87/3.44ms; maintenance debt remains charged,9checkpoints vs33. Throughput benefit isnotrepeated:64client native3.137→2.735s improvescampaign1,3.104→3.287s regressescampaign2. Fourclient benefit modest. LargeSQLbaselinevariation persists and old missesremainvalid. No universal2xclaim.

Next heldout campaign: horizon4 on100k/1Mrows4/64clients131072requests,nonaffinekeysunchanged butrequeststride7919instead130363. Bothcoprimewithdatasets. Samefullstate/frontieroracles,sync/ack/checkpointcontract. Two campaigns/cachebudgets/three repeats/sevencandidates336records. This testsout-of-samplelatency andthroughput ratherthan stacking unverifiedmechanisms.
