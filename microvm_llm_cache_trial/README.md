# MicroVM LLM 임베딩 캐시 예비 실험

자신의 Raspberry Pi 4 (ARM64 Cortex-A72), Firecracker 1.18.0, Qwen2.5-0.5B GGUF 연구 환경에만 사용하세요.

## 무엇을 실험하나

VM1이 실제 `llama-cli` 추론에서 단일 토큰 `red` 또는 `blue`를 처리할 때, VM2가 같은 GGUF 파일의 해당 임베딩 위치에서 캐시 타이밍 차이를 관찰할 수 있는지 탐색합니다.

- 파일 시작 기준 `red` 위치: 151299832
- 파일 시작 기준 `blue` 위치: 158107864
- 두 토큰 모두 Q5_0의 616바이트 행
- VM1과 VM2는 `/mnt/shared/model.gguf`에 동일한 DAX 매핑 사용
- VM2에는 레이블 파일을 제공하지 않습니다.

### 매우 중요한 실험 한계

`observer.c`는 임의의 4MiB 버퍼를 읽는 간이 eviction heuristic을 사용합니다. Cortex-A72의 캐시 연관도에 맞춘 eviction set이 아닙니다. **매 회 특정 줄을 확실히 eviction했다고 말할 수 없습니다.** 관측자의 자체 접근, 모델 재로딩, 전원/CPU 주파수 변화, 백그라운드 부하 등의 혼란 변수를 모두 통제하지 않습니다. 따라서 결과가 50%보다 높아도 실제 유출의 증거로 확정하지 말고, 반드시 no-victim 및 별개 backing file 대조군을 추가하세요. 반대로 50% 근처여도 안전성을 입증하지는 않습니다.

## 준비 — 호스트 Ubuntu SSH, 반드시 VM 두 대 모두 종료 후

이 파일들을 `~/microvm-lab/trial-kit/` 디렉터리에 복사하고:

```bash
cd ~/microvm-lab
bash trial-kit/prepare_host.sh
```

## VM 실행

호스트 SSH 터미널 1 (VM1):

```bash
cd ~/microvm-lab
taskset -c 2 ./firecracker --no-api --config-file vm1-model.json
```

호스트 SSH 터미널 2 (VM2):

```bash
cd ~/microvm-lab
taskset -c 3 ./firecracker --no-api --config-file vm2-model.json
```

두 VM의 root 콘솔에서 각각:

```bash
mkdir -p /mnt/shared
mount -t ext4 -o ro,noload,dax=always /dev/pmem0 /mnt/shared
findmnt /mnt/shared
date -u +%s
```

게스트와 호스트 시계가 비슷한지 확인하세요. 각 콘솔에서 숫자 시각을 확인하십시오.

호스트 SSH 터미널 3에서 미래 시작시간 설정:

```bash
START=$(($(date -u +%s) + 180))
echo "START=$START"
```

아래 두 명령의 `START`를 **동일한 숫자**로 교체하세요. 두 명령 모두 시작시간이 지나기 전에 실행해야 합니다.

VM2 root:

```bash
/root/observer START 20 12
```

VM1 root:

```bash
/root/victim.sh START 20 12
```

20 슬롯 × 12초의 총 240초 구간에 관측합니다. 실험 중 다른 작업을 하지 않습니다. VM1에서 label별 추론이 실행되며 VM2에 관측 CSV가 생성됩니다.

## 데이터 회수 — 두 게스트에서 `systemctl poweroff` 후 **호스트**에서

```bash
cd ~/microvm-lab
mkdir -p trial-results
sudo mkdir -p /mnt/fc-vm2-export
sudo mount -o ro,loop guest-vm2.ext4 /mnt/fc-vm2-export
sudo cp /mnt/fc-vm2-export/root/observer.csv trial-results/observer.csv
sudo umount /mnt/fc-vm2-export
sudo chown "$USER":"$USER" trial-results/observer.csv
cp trial_labels.txt trial-results/trial_labels.txt
python3 analyze_trial.py trial-results/observer.csv trial-results/trial_labels.txt
```

평가: 최초 12개 슬롯으로 점수 방향과 임계값을 정하고, 나머지 8개 슬롯을 고정된 기준으로 채점합니다. p값은 탐색적인 단순 이항 근사로, 출판 수준의 공격 입증을 의미하지 않습니다.

## 다음 단계

1. 모델을 로드하지 않은 VM1 조건에서도 같은 순서표로 관측 (음성 대조군)
2. VM2가 *서로 다른 호스트 백킹 파일*로 모델을 갖는 비공유 조건 (음성 대조군)
3. 모델을 미리 로드한 채 반복 평가하여 모델 초기화 잡음 통제
4. Cortex-A72 캐시 세트 기반 eviction 구축 후 교차 VM 검출률 재측정
5. 여러 세션에 걸친 블라인드 테스트 및 효과 크기/신뢰구간
