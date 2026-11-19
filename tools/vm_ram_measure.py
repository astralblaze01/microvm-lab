#!/usr/bin/env python3
"""RQ1 VM 수준 RAM 측정: Firecracker 게스트가 virtio-pmem DAX로 모델을 공유할 때
호스트 메모리 비용. 세 시나리오를 재서 '공유 백킹' vs '분리 백킹'의 2번째 VM 증분을 비교.

PSS 합으로 N개 firecracker 프로세스의 고유 물리 메모리를 센다. 같은 백킹 파일을 매핑한
두 프로세스의 모델 페이지는 Shared_Clean으로 공유 → PSS가 나눠 가짐 → 한 번만 셈.
Pi4 전용, 예비 하네스.
"""
import pexpect, time, os, sys

os.chdir(os.path.expanduser("~/microvm-lab"))
PROMPT = r"root@ubuntu-fc-uvm:~#"
SD = "/tmp/claude-1000/-home-ubuntu/77e6d882-3bc0-4205-af71-62730c8fa825/scratchpad"
KEYS = ("Pss","Shared_Clean","Shared_Dirty","Private_Clean","Private_Dirty","Rss")
MNT = "mkdir -p /mnt/shared && mount -t ext4 -o ro,noload,dax=always /dev/pmem0 /mnt/shared && ls -l /mnt/shared/model.gguf"

log = open(f"{SD}/vmram_run.log","w")
def say(m): print(m,flush=True); log.write(m+"\n"); log.flush()

def smaps(pid):
    d={}
    try:
        for ln in open(f"/proc/{pid}/smaps_rollup"):
            k,_,v = ln.partition(":")
            if k in KEYS: d[k]=int(v.strip().split()[0])
    except FileNotFoundError: return None
    return d

def boot(cfg, core, tag):
    say(f"[*] {tag} 부팅 ({cfg}, core{core})")
    c = pexpect.spawn(f"taskset -c {core} ./firecracker --no-api --config-file {cfg}",
                      encoding="utf-8", timeout=400)
    c.logfile_read = open(f"{SD}/vmram_{tag}.log","w")
    c.expect(PROMPT, timeout=150)
    c.sendline(MNT); c.expect(PROMPT, timeout=30)
    assert "model.gguf" in c.before, f"{tag} 모델 마운트 실패"
    # 모델 전체를 DAX로 읽어 호스트 백킹 페이지를 상주시킴(결정적)
    c.sendline("cat /mnt/shared/model.gguf > /dev/null; echo FAULTED")
    c.expect("FAULTED", timeout=120); c.expect(PROMPT, timeout=10)
    return c

def scenario(name, specs):
    # specs: [(cfg, core, tag), ...]
    children=[]
    for cfg,core,tag in specs:
        children.append((tag, boot(cfg,core,tag)))
    time.sleep(3)
    total=0; rows=[]
    for tag,c in children:
        s=smaps(c.pid)
        comm=open(f"/proc/{c.pid}/comm").read().strip()
        rows.append((tag,comm,s)); total+=s["Pss"]
    say(f"[=] 시나리오 {name}: sum(PSS)={total/1024:.1f} MiB")
    for tag,comm,s in rows:
        say(f"    {tag}[{comm}] Pss={s['Pss']/1024:.1f} SharedClean={s['Shared_Clean']/1024:.1f} "
            f"PrivDirty={s['Private_Dirty']/1024:.1f} Rss={s['Rss']/1024:.1f} MiB")
    for tag,c in children:
        try: c.sendline("systemctl poweroff")
        except Exception: pass
    for tag,c in children:
        try: c.expect(pexpect.EOF, timeout=60)
        except Exception: c.terminate(force=True)
    time.sleep(4)
    return total, rows

def main():
    os.system("pkill -f '[f]irecracker --no-api' 2>/dev/null"); time.sleep(1)
    try:
        M1,_   = scenario("1VM",        [("vm1-model.json","2","vm1")])
        Msh,_  = scenario("2VM-공유",    [("vm1-model.json","2","vm1"),("vm2-model.json","3","vm2")])
        Msep,_ = scenario("2VM-분리",    [("vm1-model.json","2","vm1"),("vm2-private.json","3","vm2")])
    finally:
        os.system("pkill -f '[f]irecracker --no-api' 2>/dev/null")
    dsh=Msh-M1; dsep=Msep-M1
    say("\n===== 요약 (호스트 RAM, firecracker PSS 합) =====")
    say(f"M(1)={M1/1024:.1f}  M(2,공유)={Msh/1024:.1f}  M(2,분리)={Msep/1024:.1f} MiB")
    say(f"2번째 VM 증분:  공유 Δ={dsh/1024:.1f} MiB   분리 Δ={dsep/1024:.1f} MiB")
    if dsep>0:
        say(f"DAX 공유로 2번째 VM 절감: {(dsep-dsh)/1024:.1f} MiB  ({(dsep-dsh)/dsep*100:.1f}%)")

if __name__=="__main__":
    main()
