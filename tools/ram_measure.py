#!/usr/bin/env python3
"""RQ1 프로세스 수준 RAM 측정: 정책 A(-lm none, 완전 분리) vs B(-lm mmap, 전체 공유).

PSS 합으로 N개 인스턴스의 실제 물리 메모리를 센다(공유 페이지는 공유자 수로 나뉘므로
sum(PSS)=고유 물리량). M(N)=sum(PSS of N insts), Δ=M(2)-M(1).
보존율 R_p = (Δ_A - Δ_p)/(Δ_A - Δ_B) * 100.  Pi4 전용, 예비 하네스.
"""
import subprocess, time, os, sys, signal

BIN = os.path.expanduser("~/microvm-lab/llama.cpp-src/build/bin/llama-cli")
MODEL = os.path.expanduser("~/microvm-lab/pmem-model-root/model.gguf")
CORES = ["2", "3"]
KEYS = ("Pss","Shared_Clean","Shared_Dirty","Private_Clean","Private_Dirty","Rss")

def smaps(pid):
    d={}
    try:
        for ln in open(f"/proc/{pid}/smaps_rollup"):
            k,_,v = ln.partition(":")
            if k in KEYS: d[k]=int(v.strip().split()[0])  # kB
    except FileNotFoundError:
        return None
    return d

def launch(policy, core):
    # 긴 생성으로 모델을 상주시킨 채 측정 창을 확보
    args=[ "taskset","-c",core, BIN, "-m",MODEL, "-lm",policy,
           "--no-warmup","--single-turn","-t","1","-c","128","-n","400",
           "-p","Write a long story about the sea." ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_resident(pid, floor_kb=350_000, timeout=120):
    """VmRSS가 모델 크기 이상으로 안정될 때까지 대기."""
    t0=time.time(); last=0; stable=0
    while time.time()-t0 < timeout:
        s=smaps(pid)
        if s is None: return False
        rss=s.get("Rss",0)
        if rss>=floor_kb and abs(rss-last)< 4000: stable+=1
        else: stable=0
        last=rss
        if stable>=3: return True
        time.sleep(1)
    return last>=floor_kb

def measure_policy(policy):
    procs=[]
    # 1 인스턴스
    p1=launch(policy, CORES[0]); procs.append(p1)
    if not wait_resident(p1.pid): print(f"[!] {policy}: inst1 상주 실패");
    time.sleep(2)
    s1=smaps(p1.pid)
    M1=s1["Pss"]
    # 2 인스턴스
    p2=launch(policy, CORES[1]); procs.append(p2)
    wait_resident(p2.pid)
    time.sleep(2)
    a=smaps(p1.pid); b=smaps(p2.pid)
    M2=a["Pss"]+b["Pss"]
    detail=dict(inst1=a, inst2=b)
    for p in procs:
        p.send_signal(signal.SIGINT);
    for p in procs:
        try: p.wait(timeout=10)
        except Exception: p.kill()
    time.sleep(3)  # 코어/캐시 정리
    return M1, M2, detail

def main():
    print(f"model={MODEL}")
    res={}
    for pol in ("none","mmap"):
        print(f"\n=== 정책 {'A(완전분리) -lm none' if pol=='none' else 'B(전체공유) -lm mmap'} ===")
        M1,M2,det=measure_policy(pol)
        d=M2-M1
        res[pol]=(M1,M2,d)
        print(f"M(1)={M1/1024:.1f} MiB  M(2)={M2/1024:.1f} MiB  Δ={d/1024:.1f} MiB")
        for nm,s in det.items():
            print(f"  {nm}: Pss={s['Pss']/1024:.1f} SharedClean={s['Shared_Clean']/1024:.1f} "
                  f"PrivDirty={s['Private_Dirty']/1024:.1f} Rss={s['Rss']/1024:.1f} MiB")
    dA=res["none"][2]; dB=res["mmap"][2]
    print("\n===== 요약 =====")
    print(f"Δ_A(분리)={dA/1024:.1f} MiB   Δ_B(공유)={dB/1024:.1f} MiB")
    if dA>0:
        print(f"2번째 인스턴스 절감: {(dA-dB)/1024:.1f} MiB  ({(dA-dB)/dA*100:.1f}% 절감)")
        print(f"보존율 R_B={ (dA-dB)/(dA-dB)*100 if dA!=dB else 100:.0f}% (정의상), R_A=0%")

if __name__=="__main__":
    main()
