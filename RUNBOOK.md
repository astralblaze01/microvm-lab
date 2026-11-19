# 재실행 런북 — MicroVM LLM 캐시 사이드채널 (2차 시행)

상태: `--no-conversation` 버그 수정 완료, 두 게스트 디스크 재프로비저닝·검증 완료.
라벨은 VM1에만 설치됨(red 10 / blue 10, 블라인드). 아래 실행만 하면 유효 데이터가 수집됨.

터미널 3개(호스트 SSH)를 띄워두고 진행. VM1/VM2 콘솔은 각 firecracker가 띄우는 시리얼 콘솔임.

---

## 1. VM 구동

**터미널 1 — VM1**
```
cd ~/microvm-lab && taskset -c 2 ./firecracker --no-api --config-file vm1-model.json
```

**터미널 2 — VM2**
```
cd ~/microvm-lab && taskset -c 3 ./firecracker --no-api --config-file vm2-model.json
```

부팅 후 각 VM의 `root@ubuntu-fc-uvm:~#` 프롬프트가 뜨면 다음 단계.

## 2. 두 VM에서 공유 모델 마운트 (VM1 콘솔, VM2 콘솔 각각)

```
mkdir -p /mnt/shared && mount -t ext4 -o ro,noload,dax=always /dev/pmem0 /mnt/shared && findmnt /mnt/shared && date -u +%s
```

`/mnt/shared`가 보이고 시각(초)이 호스트와 비슷한지 확인.

## 3. 공통 START 계산 (터미널 3 — 호스트)

```
START=$(($(date -u +%s) + 180)); echo "START=$START"
```

출력된 숫자를 복사. 아래 두 명령의 `START` 자리에 **같은 숫자**를 넣고, 그 시각이 지나기 전에 둘 다 실행.

## 4. 관측 시작 — VM2 먼저, 그다음 VM1

**VM2 콘솔** (START를 숫자로 교체):
```
/root/observer START 20 12
```

**VM1 콘솔** (같은 숫자로 교체):
```
/root/victim.sh START 20 12
```

20 슬롯 × 12초 = 240초. 실행 중 호스트/VM에서 다른 작업 금지.
VM1 로그에 `slot=0 label=... exit=0` 이 보이면 정상(이전엔 exit=1 이었음).

## 5. 종료 — 두 VM 각 콘솔

```
systemctl poweroff
```

두 콘솔 모두 종료되면(firecracker 프로세스 종료) 회수 단계로.

---

## 6. 데이터 회수 + 분석 (호스트) — 이 부분은 Claude에게 맡겨도 됨

```
cd ~/microvm-lab && sudo mkdir -p /mnt/fc-vm2-export && sudo mount -o ro,loop guest-vm2.ext4 /mnt/fc-vm2-export && sudo cp /mnt/fc-vm2-export/root/observer.csv trial-results/observer.csv && sudo umount /mnt/fc-vm2-export && sudo chown "$USER":"$USER" trial-results/observer.csv && cp trial_labels.txt trial-results/trial_labels.txt
```

```
python3 analyze_trial.py trial-results/observer.csv trial-results/trial_labels.txt
```

> 주의: 이 분석은 탐색적 proxy 테스트이지 취약점 입증이 아님. 50% 초과여도 반드시 대조군
> (no-victim, private-backing)과 반복 세션으로 검증해야 함. README '다음 단계' 참고.
