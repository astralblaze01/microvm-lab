#!/bin/bash
# Host ubuntu@tennessine only, all VMs must be OFF.
set -euo pipefail
cd "$HOME/microvm-lab"
if pgrep -x firecracker >/dev/null; then
   echo 'ERROR: Firecracker running. Shut down BOTH guests first.' >&2
   exit 1
fi
BUNDLE="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f guest-vm1.ext4 || ! -f guest-vm2.ext4 ]]; then
   echo 'ERROR: Guest images missing in ~/microvm-lab' >&2; exit 1
fi
if [[ ! -f llama.cpp-src/build/bin/llama-cli ]]; then
   echo 'ERROR: llama-cli missing' >&2; exit 1
fi
if [[ ! -f model-pmem.ext4 ]]; then
   echo 'ERROR: model-pmem.ext4 missing' >&2; exit 1
fi
# Exactly 6 red and 6 blue in training, 4 and 4 in held-out test.
python3 - <<'PY'
from secrets import SystemRandom
from pathlib import Path
rnd = SystemRandom()
labels = ['red']*6 + ['blue']*6
rnd.shuffle(labels)
tail = ['red']*4 + ['blue']*4
rnd.shuffle(tail)
labels += tail
Path('trial_labels.txt').write_text('\n'.join(labels)+'\n')
print('Generated 20 balanced, hidden trial labels (VM1 only)')
PY

gcc -O2 -std=gnu11 -Wall -Wextra -static "$BUNDLE/observer.c" -o observer
file observer
for i in 1 2; do
    mnt="/mnt/fc-vm${i}-trial"
    sudo mkdir -p "$mnt"
    sudo mount -o loop "guest-vm${i}.ext4" "$mnt"
    if [[ "$i" == 1 ]]; then
        sudo install -m 755 "$BUNDLE/victim.sh" "$mnt/root/victim.sh"
        sudo install -m 600 trial_labels.txt "$mnt/root/trial_labels.txt"
    else
        sudo install -m 755 observer "$mnt/root/observer"
    fi
    sync
    sudo umount "$mnt"
    echo "VM$i installed"
done
cp "$BUNDLE/analyze.py" analyze_trial.py
printf '\nReady. Leave trial_labels.txt private from VM2.\n'
printf 'Start both VMs, mount /dev/pmem0 in guests, then run synchronized commands.\n'
