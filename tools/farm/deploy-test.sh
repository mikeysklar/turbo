#!/bin/bash
# Deploy the shim + pixels to every farm board and run the code.py body over the REPL.
set -u; cd ~/turbo/shim; R=~/turbo/shim/results; rm -rf $R; mkdir -p $R
BOARDS="RP2040:3-3.2:adafruit_metro_rp2040 M4:3-3.3.1:metro_m4_airlift_lite M0:3-3.3.2:metro_m0_express nRF52840:3-3.3.3:feather_nrf52840_express ESP32-S2:3-3.3.4.1:adafruit_metro_esp32s2 RP2350:3-3.3.4.2:adafruit_metro_rp2350 ESP32-S3:3-3.3.4.3:adafruit_metro_esp32s3 STM32F405:3-3.3.4.4:feather_stm32f405_express"
for e in $BOARDS; do nm=${e%%:*}; r=${e#*:}; P=${r%%:*}; id=${r#*:}
  blk=$(ls -d /sys/bus/usb/devices/$P/$P:1.*/host*/target*/*/block/* 2>/dev/null | head -1); mnt=$(findmnt -n -o TARGET /dev/$(basename ${blk:-x})1 2>/dev/null)
  [ -f "${mnt:-}/boot_out.txt" ] && grep -q "Board ID:$id" "$mnt/boot_out.txt" || { echo "$nm: no mount or wrong board" | tee $R/$nm.out; continue; }
  mkdir -p "$mnt/lib/turbo/armv6m" "$mnt/lib/turbo/armv7emsp" "$mnt/src"
  cp lib/turbo.py "$mnt/lib/"; cp lib/turbo/turbo.json "$mnt/lib/turbo/"; cp src/pixels.py "$mnt/src/"
  cp lib/turbo/armv6m/pixels.mpy "$mnt/lib/turbo/armv6m/"; cp lib/turbo/armv7emsp/pixels.mpy "$mnt/lib/turbo/armv7emsp/"
  sync; echo "$nm: deployed to $mnt ($(head -1 $mnt/boot_out.txt | cut -c1-60))"
done
sleep 5
for e in $BOARDS; do nm=${e%%:*}; r=${e#*:}; P=${r%%:*}
  TTY=$(readlink -f /dev/serial/by-path/*usb-0:${P#3-}:1.0 2>/dev/null) || continue
  ( timeout 600 python3 - "$TTY" "$nm" > $R/$nm.out 2>&1 <<'PY'
import sys; sys.path.insert(0,"/home/sklarm/cp-1030/tools"); import pyboard
tty, nm = sys.argv[1], sys.argv[2]
pyb = pyboard.Pyboard(tty, 115200); pyb.enter_raw_repl()
try:
    out = pyb.exec_(open("/home/sklarm/turbo/shim/code.py").read(), timeout=500).decode().strip()
    print(nm, out.replace("\n", " | "))
except pyboard.PyboardError as e:
    print(nm, "FAILED:", str(e)[:400].replace("\n"," | "))
pyb.exit_raw_repl(); pyb.close()
PY
  ) &
done
wait; echo "### ALLDONE"
