# microvm-lab — MicroVM 간 LLM 가중치 공유 예비 실험

Raspberry Pi 4 (Cortex-A72), Firecracker 1.18.0, Qwen2.5-0.5B GGUF 환경에서 수행한 **예비 실험**(pilot) 기록.
연구 기획안상 예비 실험 데이터는 본분석에서 제외되며, 표본 수·도구 점검 용도로만 쓴다.

두 갈래를 다룬다. (1) RQ1 — 가중치 공유의 **메모리 이득** 측정(Pi4에서 깨끗하게 성립). (2) RQ2 — 교차 VM
**캐시 사이드채널** 예비 측정(이 naive probe로는 신호 분해 불가, 도구 한계를 확인).

## 구성
- `microvm_llm_cache_trial/` — 사이드채널 실험 키트 (victim.sh, observer.c, analyze.py, prepare_host.sh)
- `tools/` — 헤드리스 VM 드라이버(대조군) + RAM 측정 하네스(`ram_measure.py`, `vm_ram_measure.py`)
- `trial-results/` — 원시 데이터와 결과 요약 (`RESULTS.md`, `RQ1_ram_pilot.md`)
- `RUNBOOK.md` — 2-VM 동기 실행 절차
- `vm*.json` — Firecracker 설정

## RQ1 — 가중치 공유 메모리 이득 (Pi4 실측)
모델을 공유하면 2번째 인스턴스가 모델을 다시 올리지 않는다. 2번째 인스턴스의 호스트 RAM 증분:

| 층위 | 분리(A) | 공유(B) | 절감 |
|---|---|---|---|
| 프로세스 (`-lm none` vs `-lm mmap`) | 540 MiB | 78 MiB | ~85% |
| MicroVM (virtio-pmem DAX, 별도 vs 공유 백킹) | 586 MiB | 115 MiB | ~80% |

물리 공유 직접 증거: 공유 시 모델 ~472 MiB가 `Shared_Clean`으로 두 프로세스에 걸쳐 한 번만 존재.
엣지 ARM에서도 공유 이득이 프로세스·VM 두 층위에서 성립. 자세한 수치는 `trial-results/RQ1_ram_pilot.md`.

## RQ2 — 교차 VM 사이드채널 (예비, 음성)
| 조건 | held-out 정확도 | p |
|---|---|---|
| 본런 (공유 백킹, victim 추론) | 4/8 = 50.0% | 0.637 |
| no-victim (VM1 미실행) | 3/8 = 37.5% | 0.855 |
| private-backing (VM2 별도 백킹) | 5/8 = 62.5% | 0.363 |

세 조건 모두 슬롯별 입력을 구분하지 못함. 결정적 원인은 `observer.c`의 측정 순서(비우기→대기→읽기가
아니라 대기→비우기→읽기라 피해자 접근을 볼 수 없음)와 측정 잡음(배리어 오버헤드 ~1µs). 즉 **"유출 없음"이
아니라 "이 도구로는 관측 불가"**. 자세한 해석은 `trial-results/RESULTS.md` 참고.

## 제외한 것
게스트 디스크 이미지(*.ext4), 모델(*.gguf), 커널, Firecracker 바이너리, llama.cpp 소스는 용량 때문에 포함하지 않음.
