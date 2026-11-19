# 2차 시행 결과 — MicroVM LLM 임베딩 캐시 사이드채널

- 일시: 2026-11-19 (KST) 두 번째 실행
- 환경: Raspberry Pi 4 (Cortex-A72), Firecracker 1.18.0, Qwen2.5-0.5B Q4_K_M
- 구성: VM1(victim, core2) / VM2(observer, core3), 공유 pmem DAX `model-pmem.ext4`(RO)
- 슬롯: 20 × 12초 = 240초, 라벨 red 10 / blue 10 (블라인드, VM1 전용)

## 1차 대비 변경
- 1차 실패 원인: `victim.sh`의 미지원 플래그 `--no-conversation` → 전 슬롯 `exit=1` (무효).
- 수정: 해당 플래그 제거(`--single-turn`이 단일 턴 후 종료 보장). 호스트 원본 수정 + 게스트 재설치.

## 데이터 유효성
- victim.csv: 20슬롯 **전부 `exit=0`** → 실제 추론 정상 수행 (유효).
- observer.csv: 3261 샘플 (슬롯당 ~163).

## 분석 (analyze_trial.py, 12 train / 8 held-out)
- Training red mean=101.8, blue mean=111.0, cutoff=106.4
- **HELD-OUT ACCURACY: 4/8 = 50.0%**
- Naive one-sided Binomial(0.5) p = 0.637

## 해석
- held-out 정확도 50% = **우연 수준**. 이 구성에서는 교차 VM 유출 신호가 관측되지 않음.
- score(blue_p10 − red_p10)가 거의 전 슬롯 111ns로 **상수에 가까움** → 측정값이 victim 입력(red/blue)과
  무관한 구조적 오프셋에 지배됨. 이는 README가 경고한 대로 `observer.c`의 4MiB 단순 sweep이
  Cortex-A72 캐시 세트/연관도에 맞춘 진짜 eviction set이 아니기 때문으로 보임.
- 즉 "유출 없음을 입증"한 게 아니라, **naive probe로는 분해능이 부족**하다는 (예상된) 음성 결과.

## 다음 단계 (논문용)
1. 음성 대조군 A: VM1이 모델 미로드 조건에서 같은 순서표 관측.
2. 음성 대조군 B: VM2가 *서로 다른 백킹 파일*로 모델을 갖는 비공유 조건.
3. 모델 사전 로드 상태 반복 측정으로 초기화 잡음 통제.
4. Cortex-A72 캐시 세트 기반 eviction set 구축 후 재측정 (핵심 개선).
5. 여러 랜덤 세션 블라인드 반복 + 효과 크기/신뢰구간.

## 산출물
- trial-results/observer.csv, victim.csv, trial_labels.txt — 원시 데이터(재현/표용).

---

# 대조군 1 — no-victim (VM1 미실행)

- 구성: VM2만 부팅(observer 20×12초), VM1은 아예 실행 안 함 → victim 활동 0.
- 분석 기준: 본런과 동일한 trial_labels.txt (blind).

| 조건 | held-out | p | red_median | blue_median | blue−red |
|---|---|---|---|---|---|
| 본런 (victim 추론) | 50.0% | 0.637 | 925 | 1037 | +112ns |
| no-victim (VM1 off) | 37.5% | 0.855 | 1222 | 1222 | 0ns |

## 해석
1. **비밀 비유출 재확인**: 두 조건 모두 held-out 우연 수준 → observer는 슬롯별 red/blue를 못 맞춤.
2. **victim 유무의 거친 흔적은 존재**: victim 실행 시 (a) 두 위치 접근이 전반적으로 빨라짐
   (1222→925/1037ns, 공유 모델 반복 로드로 페이지 warm), (b) blue가 red보다 **상수 +112ns** 느림.
   이 격차는 전 슬롯 동일 → 그 슬롯 라벨과 무관 → 분류는 우연.
3. no-victim에선 blue−red 격차가 **0ns**로 소멸 → +112ns는 victim 활동의 구조적 부산물이지
   비밀 의존 신호가 아님.

## 결론 (이 두 시행 기준)
naive 4MiB sweep probe는 **"victim이 돌고 있다"는 coarse presence 신호**는 감지하나,
**"어떤 토큰(red/blue)인가"라는 fine-grained 비밀**은 분해하지 못함. 유출 미검출(음성),
단 분해능 한계에 의한 것이지 안전성 증명은 아님.

## 산출물 추가
- trial-results/novictim_observer.csv — no-victim 원시 데이터.

---

# 대조군 2 — private-backing (VM2만 별도 백킹 파일)

- VM1=공유 model-pmem.ext4 에서 victim 추론(20슬롯 exit=0), VM2=model-pmem-private.ext4(복사본, 다른 inode)에서 observer.
- held-out 5/8 = 62.5%, p=0.363 (우연과 구분 안 됨). 학습 구간 red/blue 평균 점수 -379.5 vs -376.3 → 라벨 정보 없음.

| 조건 | red_med | blue_med | blue−red |
|---|---|---|---|
| 본런(공유) | 925 | 1037 | +112 |
| no-victim | 1222 | 1222 | 0 |
| private-backing | 1018 | 611 | -407 |

## 해석 (주의)
- 비공유에서도 blue−red 격차(-407ns)가 생김 → 이 격차는 **백킹 파일의 물리 배치(캐시 세트 aliasing)에 따른 매핑 고유 오프셋**이며
  victim 입력과 무관. 따라서 본런의 +112ns도 "유출 신호"가 아니라 같은 종류의 오프셋일 가능성이 큼.
- 세 조건 모두 슬롯별 라벨 판별 불가. 이 Pi4 naive probe로는 RQ2 양성 대조가 성립하지 않음 → 예비 실험으로만 사용.
- 남은 한계: 조건 간 오프셋이 달라 단순 비교 불가(교란). 본실험에서는 같은 매핑 안에서 A/B 비교로 설계해야 함.
