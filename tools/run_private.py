#!/usr/bin/env python3
# private-backing 대조군 (순차 부팅판):
#   VM1 = victim (공유 model-pmem.ext4), VM2 = observer (별도 model-pmem-private.ext4)
import pexpect, sys, time, os

os.chdir(os.path.expanduser("~/microvm-lab"))
PROMPT = r"root@ubuntu-fc-uvm:~#"
LEAD = 60
SLOTS, SLOT = 20, 12
SD = "/tmp/claude-1000/-home-ubuntu/77e6d882-3bc0-4205-af71-62730c8fa825/scratchpad"

main = open(f"{SD}/private_run.log", "w")
def log(m): print(m, flush=True); main.write(m+"\n"); main.flush()

MNT = "mkdir -p /mnt/shared && mount -t ext4 -o ro,noload,dax=always /dev/pmem0 /mnt/shared && ls -l /mnt/shared/model.gguf"
vm1 = None; vm2 = None

def poweroff_both():
    for v in (vm1, vm2):
        if v is None: continue
        try: v.sendline("systemctl poweroff")
        except Exception: pass
    for v in (vm1, vm2):
        if v is None: continue
        try: v.expect(pexpect.EOF, timeout=60)
        except Exception: v.terminate(force=True)

try:
    log("[*] VM1 부팅")
    vm1 = pexpect.spawn("taskset -c 2 ./firecracker --no-api --config-file vm1-model.json",
                        encoding="utf-8", timeout=400)
    vm1.logfile_read = open(f"{SD}/private_vm1.log","w")
    vm1.expect(PROMPT, timeout=150); log("[*] VM1 로그인")

    log("[*] VM2 부팅 (VM1 idle 상태에서 단독)")
    vm2 = pexpect.spawn("taskset -c 3 ./firecracker --no-api --config-file vm2-private.json",
                        encoding="utf-8", timeout=400)
    vm2.logfile_read = open(f"{SD}/private_vm2.log","w")
    vm2.expect(PROMPT, timeout=150); log("[*] VM2 로그인")

    vm1.sendline(MNT); vm1.expect(PROMPT, timeout=30)
    assert "model.gguf" in vm1.before, "VM1 모델 마운트 실패"
    vm2.sendline(MNT); vm2.expect(PROMPT, timeout=30)
    assert "model.gguf" in vm2.before, "VM2 모델 마운트 실패"
    log("[*] 두 VM 모델 마운트 OK (VM1=공유, VM2=비공유)")

    start = int(time.time()) + LEAD
    log(f"[*] START={start} (now+{LEAD}s)")
    vm2.sendline(f"/root/observer {start} {SLOTS} {SLOT}")
    vm1.sendline(f"/root/victim.sh {start} {SLOTS} {SLOT}")
    log("[*] observer/victim 실행, 완료 대기(~240s)")

    vm2.expect(r"Done: /root/observer\.csv", timeout=LEAD + SLOTS*SLOT + 120)
    log("[*] observer 완료")
    vm1.expect(r"Done: /root/victim\.csv and", timeout=90)
    log("[*] victim 완료")
    vm1.expect(PROMPT, timeout=20)
    vm1.sendline("awk -F, 'NR>1{c[$6]++}END{for(k in c)print \"exit=\"k\":\"c[k]}' /root/victim.csv")
    vm1.expect(PROMPT, timeout=20)
    log("[*] VM1 victim exit 분포:\n"+vm1.before.strip())
    vm2.expect(PROMPT, timeout=20)
    vm2.sendline("wc -l /root/observer.csv"); vm2.expect(PROMPT, timeout=20)
    log("[*] observer.csv:\n"+vm2.before.strip())

    log("[*] 두 VM poweroff"); poweroff_both(); log("[*] 완료")
except Exception as e:
    log(f"[!] 예외: {type(e).__name__}: {e}")
    log("[!] VM1 최근:\n"+((vm1.before if vm1 else "") or "")[-500:])
    log("[!] VM2 최근:\n"+((vm2.before if vm2 else "") or "")[-500:])
    poweroff_both(); sys.exit(2)
finally:
    main.close()
