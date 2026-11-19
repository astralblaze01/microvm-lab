# microvm-lab — MicroVM 간 LLM 가중치 공유 예비 실험

Raspberry Pi 4 (Cortex-A72), Firecracker 1.18.0, Qwen2.5-0.5B GGUF 환경에서 수행한 **예비 실험**(pilot) 기록.
연구 기획안상 예비 실험 데이터는 본분석에서 제외되며, 표본 수·도구 점검 용도로만 쓴다.

## 구성
- `microvm_llm_cache_trial/` — 실험 키트 (victim.sh, observer.c, analyze.py, prepare_host.sh)
- `tools/` — 헤드리스 VM 구동 드라이버 (no-victim, private-backing 대조군)
- `trial-results/` — 원시 데이터와 결과 요약 (`RESULTS.md`)
- `RUNBOOK.md` — 2-VM 동기 실행 절차
- `vm*.json` — Firecracker 설정

## 결과 요약
| 조건 | held-out 정확도 | p |
|---|---|---|
| 본런 (공유 백킹, victim 추론) | 4/8 = 50.0% | 0.637 |
| no-victim (VM1 미실행) | 3/8 = 37.5% | 0.855 |
| private-backing (VM2 별도 백킹) | 5/8 = 62.5% | 0.363 |

세 조건 모두 슬롯별 입력을 구분하지 못함. naive 4MiB eviction probe의 분해능 한계로 양성 대조가 성립하지 않음.
자세한 해석은 `trial-results/RESULTS.md` 참고.

## 제외한 것
게스트 디스크 이미지(*.ext4), 모델(*.gguf), 커널, Firecracker 바이너리, llama.cpp 소스는 용량 때문에 포함하지 않음.
