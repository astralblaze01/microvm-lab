#!/bin/bash
# VM1 only. No label or logfile is disclosed to VM2.
set -u
if [[ $# != 3 ]]; then
  echo "Usage: /root/victim.sh START_UNIX SLOTS SLOT_SECONDS" >&2
  exit 2
fi
START=$1
SLOTS=$2
SLOT_SECONDS=$3
if (( START < 1 || SLOTS < 1 || SLOT_SECONDS < 5 )); then
  echo 'Invalid arguments' >&2
  exit 2
fi
if (( $(date +%s) > START + 1 )); then
  echo 'Start time already passed' >&2
  exit 2
fi
mapfile -t labels < /root/trial_labels.txt
if (( ${#labels[@]} != SLOTS )); then
  echo "Expected $SLOTS labels; found ${#labels[@]}" >&2
  exit 2
fi
mkdir -p /root/victim_out
printf 'slot,label,scheduled_unix,begin_unix,end_unix,exit_code\n' > /root/victim.csv
echo "VICTIM start=$START slots=$SLOTS slot_seconds=$SLOT_SECONDS"
for ((i=0; i<SLOTS; i++)); do
    label=${labels[$i]}
    if [[ "$label" != red && "$label" != blue ]]; then
      echo "Invalid label: $label" >&2; exit 2
    fi
    scheduled=$((START + i * SLOT_SECONDS + 2))
    while (( $(date +%s) < scheduled )); do sleep 0.1; done
    begin=$(date +%s.%N)
    /root/llama-cli \
      -m /mnt/shared/model.gguf \
      -lm mmap --no-repack \
      --single-turn --no-warmup \
      -t 1 -c 64 -n 1 \
      -p "$label" \
      > "/root/victim_out/slot_${i}.txt" 2>&1
    status=$?
    end=$(date +%s.%N)
    printf '%d,%s,%d,%s,%s,%d\n' "$i" "$label" "$scheduled" "$begin" "$end" "$status" >> /root/victim.csv
    echo "slot=$i label=$label exit=$status began=$begin ended=$end"
done
echo 'Done: /root/victim.csv and /root/victim_out/'
