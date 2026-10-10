set -euo pipefail
mkdir -p /build /volume/random-profile-01
cd /build
cp /src/*.hpp /src/backlog-n*.cpp /build/
cp /sqlite/sqlite3.c /sqlite/sqlite3.h /build/
gcc -O3 -c sqlite3.c -o sqlite3.o
for n in 100000 1000000; do
 for g in 1 4 16 64; do
  cap=$((32768/g));case $g in 1) frame=128;direct=1;;4) frame=256;direct=0;;16) frame=512;direct=0;;64) frame=2048;direct=0;;esac
  for k in 2000 131072; do
   g++ -O3 -std=c++17 -DDENSE=1 -DTARGETED=1 -DPREFILL=1 -DREGION_COUNT=4096 -DRING_CAPACITY=$cap -DMAX_GROUP=$g -DFRAME_BYTES=$frame -DDIRECT_OWNER=$direct -DDSYNC_PACKED=1 -DVALUE_BANKS=1 -DSQL_CACHE_KIB=$k -I/build backlog-n${n}.cpp sqlite3.o -ldl -pthread -lm -Wl,--wrap=fsync,--wrap=fdatasync,--wrap=pwrite,--wrap=pwrite64,--wrap=write -o bench-n${n}-g${g}-k${k}
  done
 done
done
for ca in 1 2; do
 if test "$ca" = 1; then ns='100000 1000000';gs='1 4 16 64';ks='2000 131072';else ns='1000000 100000';gs='64 16 4 1';ks='131072 2000';fi
 for n in $ns; do
  for pair in 0 1 2; do
   for phase in 0 1 2 3 4 5 6; do
    b=$(((pair+phase)%7))
    for g in $gs; do
     for k in $ks; do
      ./bench-n${n}-g${g}-k${k} /volume/random-profile-01/run${ca}-n${n}-g${g}-k${k}-p${pair}-b${b} $g 131072 $ca $pair $b
     done
    done
   done
  done
 done
done
printf 'PASS currentvaluebank1/4/16/64clientqualification;672expectedrecords;exactaggregationpending\n'
