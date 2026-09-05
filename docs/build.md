# Build turbo firmware

Just the commands. Builds the four ARM boards at a stock CircuitPython tag and
the two ESP32 boards (S2, S3) from the fork branch, native flag on, then
publishes a release with the `.uf2` files.

```sh
R=mikeysklar/turbo
TAG=10.3.0            # any adafruit/circuitpython release tag
REF=esp32-native      # fork branch for the ESP32 boards

# kick off the build
gh workflow run firmware.yml -R $R -f cp_version=$TAG -f esp32_ref=$REF

# watch it (waits, streams job status, exits non-zero if it fails)
gh run watch -R $R $(gh run list -R $R -w firmware.yml -L1 --json databaseId --jq '.[0].databaseId')

# download every firmware file from the release into ./turbo-$TAG
gh release download cp-$TAG -R $R -D turbo-$TAG

# or just one board's uf2
gh release download cp-$TAG -R $R -p '*metro_rp2350*.uf2'
gh release download cp-$TAG -R $R -p '*metro_esp32s3*.uf2'
```

Flash an RP board: drag the `.uf2` onto the RPI-RP2 / RP2350 drive, or

```sh
cp turbo-$TAG/*metro_rp2350*.uf2 /Volumes/RP2350/     # macOS
```
