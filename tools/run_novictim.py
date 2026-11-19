#!/usr/bin/env python3
# no-victim 대조군: VM2만 부팅해 observer 240초 실행 후 poweroff.
# VM1은 실행하지 않음 → victim 활동 전혀 없음.
import pexpect, sys, time, os

os.chdir(os.path.expanduser("~/microvm-lab"))
PROMPT = r"root@ubuntu-fc-uvm:~#"
LEAD = 45
SLOTS, SLOT = 20, 12

logf = open("/tmp/claude-1000/-home-ubuntu/77e6d882-3bc0-4205-af71-62730c8fa825/scratchpad/novictim_run.log", "w")
def log(m):
    print(m, flush=True); logf.write(m+"\n"); logf.flush()

child = pexpect.spawn("taskset -c 3 ./firecracker --no-api --config-file vm2-model.json",
                      encoding="utf-8", timeout=400)
child.logfile_read = logf
try:
    log("[*] 부팅 대기...")
    child.expect(PROMPT, timeout=90)
    log("[*] 로그인 OK, pmem 마운트")
    child.sendline("mkdir -p /mnt/shared && mount -t ext4 -o ro,noload,dax=always /dev/pmem0 /mnt/shared && ls -l /mnt/shared/model.gguf")
    child.expect(PROMPT, timeout=30)
    if "model.gguf" not in child.before:
        log("[!] 모델 마운트 실패:\n"+child.before); child.sendline("systemctl poweroff"); sys.exit(1)

    start = int(time.time()) + LEAD
    log(f"[*] START={start} (now+{LEAD}s), observer {SLOTS}x{SLOT}s 실행")
    child.sendline(f"/root/observer {start} {SLOTS} {SLOT}")
    # observer는 끝에 stderr로 'Done: /root/observer.csv' 출력 후 프롬프트 복귀
    child.expect(r"Done: /root/observer\.csv", timeout=LEAD + SLOTS*SLOT + 60)
    log("[*] observer 완료")
    child.expect(PROMPT, timeout=30)
    child.sendline("sync; wc -l /root/observer.csv")
    child.expect(PROMPT, timeout=20)
    log("[*] observer.csv 줄수:\n"+child.before.strip())
    log("[*] poweroff")
    child.sendline("systemctl poweroff")
    child.expect(pexpect.EOF, timeout=60)
    log("[*] VM 종료 완료")
except Exception as e:
    log(f"[!] 예외: {type(e).__name__}: {e}")
    log("[!] 최근 버퍼:\n"+ (child.before or "")[-800:])
    try: child.sendline("systemctl poweroff"); child.expect(pexpect.EOF, timeout=60)
    except Exception: child.terminate(force=True)
    sys.exit(2)
finally:
    logf.close()
