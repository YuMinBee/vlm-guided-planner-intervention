# VLM-Guided Planner Intervention

카메라 관측과 같은 시점의 차량 기준 경로 정보를 VLM에 전달하고, 비동기로
받은 주행 의도를 검증해 기존 계획기의 경로·속도 선택에 반영한다. VLM은
고수준 의도를 제공하고, 연속 궤적과 저수준 제어는 계획기와 제어기가 담당한다.

이 저장소에는 독립적인 비동기 런타임·관측 좌표 변환 참조 코드와 로컬 통합
검증 기록이 있다. HiP-AD 통합 코드, 가중치, 데이터와 원본 실행 산출물은 포함하지 않는다.

## 동작 구조

```mermaid
flowchart LR
    A[카메라·위치·방향·경로 관측] --> B[관측 시점의 차량 기준 목표점]
    A --> C[기존 계획기의 후보 경로·속도]
    B --> D[최신 프레임 큐와 VLM worker]
    D --> E[원본 시점·명령·유효성 검사]
    E --> F[경로 의도와 회전 완료 상태]
    C --> G[경로·속도 공동 선택과 운동 예측]
    F --> G
    G --> H[동일한 조향 계산으로 실행]
```

1. **입력 기준을 맞춘다.** 목표점에서 관측 당시 차량 위치를 빼고 전방·우측
   축에 투영한다. 프롬프트는 x=전방, y=우측을 사용한다. 카메라와 좌표는 같은
   프레임·시뮬레이션 시각으로 묶는다.
2. **추론을 비동기로 처리한다.** 크기1 큐는 대기 중인 최신 관측만 유지한다.
   제어 루프는 VLM 응답을 기다리지 않고, 결과를 원본 시각·TTL·출력 유효성에
   따라 수용한다. 참조 런타임은 신뢰도 임계값도 검사할 수 있다.
3. **의도를 실행 상태에 연결한다.** 로컬 통합은 경로가 뒷받침하는 회전의
   관측 시점 출구를 기억한다. 다음 내비게이션 명령이 바뀌었다는 이유만으로
   회전을 끝내지 않고, 현재 위치·방향으로 완료를 확인한다. 정지 명령은 우선한다.
4. **경로와 속도를 함께 선택한다.** 실제 조향에 사용할 공간 경로와 속도를
   조합해 경로 기하와 예측 장애물을 검사한다. 후보 번호만으로 회전 의미를
   단정하지 않으며, 필요한 경로 후보와 감속·정지 선택을 고려한다.
5. **검사한 계획을 실행한다.** 로컬 제어 구성은 후보 운동 예측과 실제 조향에
   같은 pure-pursuit 계산을 사용하고, 기존 종방향 PID를 유지한다.

첫 두 단계의 최소 참조 코드가 `src/`에 있다. 회전 상태·공동 선택·제어까지
포함한 전체 흐름은 로컬 통합의 설계이며, 이 저장소 설치만으로 자동 활성화되지는 않는다.
[설계 문서](docs/concept.md)에 각 단계의 책임과 범위를 설명한다.

## 참조 코드 사용

```python
from vlm_async_gate import FrameSample, capture_navigation

navigation = capture_navigation(
    frame_id=10, simulation_time_s=1.0,
    position_xy=(100, 200),
    forward_xy=(0, -1), right_xy=(1, 0),
    near_target_xy=(102, 190), far_target_xy=(97, 180),
)
assert navigation.near_forward_right == (10.0, 2.0)
payload = {"navigation": navigation, "prompt_fields": navigation.prompt_values()}
sample = FrameSample(navigation.frame_id, navigation.simulation_time_s, payload)
# 실제 제출 시 payload에 같은 관측 시점의 카메라 입력을 함께 넣는다.
# worker.submit(sample)
```

세계 좌표계와 단위는 호출자가 일치시켜야 한다. 전방·우측 단위축을 명시하므로
특정 시뮬레이터의 방향각 규약에 의존하지 않는다. 지연 응답이 도착할 때 새
차량 위치로 과거 입력을 다시 변환하지 않는다.

- [좌표 계약과 예제](docs/capture-coordinates.md)
- [비동기 시간 계약](docs/async-runtime.md)
- 코드: `src/vlm_async_gate/coordinates.py`, `src/vlm_async_gate/runtime.py`
- 테스트: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

## 검증 결과

기존 HiP-AD가 해결하지 못한 열린 차량 문 회피 사례에서는 비동기 VLM의
`change_lane_left`가 검증된 인접 차선 목표점과 제한된 궤적 보정을 활성화했고,
경로를100% 완주하며 충돌·차선 이탈0, 종합 점수100을 기록했다.
이것은 초기 통합 구성의 실패 상황 보완 사례이며 전체 데이터셋의 우월성을 뜻하지 않는다.
[당시 비동기 검증 기록](docs/async-validation.md)에 조건과 개입 내역을 보존한다.

현재 로컬 경로·속도·조향 구성의 개발 비교는 다음과 같다. 비교 기준에도
동일한 차량 기준 좌표 입력을 적용했다.

| 경로27532 구성 | 시드 | 구조물 충돌 | 차량 충돌 | 완료율 | Driving Score |
|---|---:|---:|---:|---:|---:|
| 좌표가 일치하는 기존 구성 | 0 | 1 | 1 | 100% | 39.0 |
| 경로·속도·조향 구성 | 0 | 0 | 0 | 100% | 100.0 |
| 경로·속도·조향 구성 | 1 | 0 | 0 | 100% | 100.0 |

같은 고정 구성은 기존 성공 경로2989·3482도 충돌 없이 완주했다. 확인 범위는
선정3개 경로의4회 완주다. 좌표 입력 하나나 VLM 자체의 효과로 이 결과를
설명하지 않으며, 학습 연결층의 성능도 아니다.
[제어 검증 기록](docs/grounded-control-validation.md)에 조향기 단독 비교,
실행 조건과 한계를 정리한다. [동기식 초기 검증](docs/verified-prototype.md)은
별도 구성의 기록으로 남긴다.

## 구현과 평가 범위

공개 참조 코드는 좌표 변환과 최신 프레임·TTL 런타임을 구현하고 모의 테스트를
통과했다. 전체 로컬 제어 통합은 별도로 검증했으며, 공개 참조 코드와 동일한
배포물은 아니다. 제어 코드 패키징 후 새 주행은 실행하지 않았다.

CARLA의 시뮬레이션 시간과 실제 추론 시간은 다르다. 제어 루프가 VLM을 직접
기다리지 않는다는 사실만으로 실시간20Hz 주행이나 지연 강인성이 입증되지는
않는다. 경로 선택도 예측 장애물과 근사 운동 모델에 의존한다.

## 공개 범위와 권리

포함하는 것은 독립 참조 코드, 설계 설명, 사실적 집계 검증 기록이다.
다음 자료는 포함하지 않는다.

- HiP-AD 등 제3자 소스·설정·수정 패치·통합 코드
- 모델 가중치, 데이터셋, 이미지, 영상, 논문 그림
- 원본 실행 로그와 프레임별 평가 산출물

배경 계획기는 [HiP-AD](https://github.com/nullmax-vision/HiP-AD)이며,
본 저장소는 공식 프로젝트나 제휴 구현이 아니다.
[제3자 자료 범위](THIRD_PARTY.md), [권리 고지](RIGHTS.md),
[공개 체크리스트](docs/publication-checklist.md)를 따른다.
현재 별도 오픈소스 라이선스를 부여하지 않는다.

## English summary

VLM-guided planner intervention binds camera observations and ego-frame navigation
to one capture timestamp, validates asynchronous intent, and uses it in planner
execution. The local control design combines source-time turn completion, joint
path/speed selection and a steering model shared by candidate rollout and control.

This repository implements only the independent coordinate and latest-frame runtime
references. Full planner integration remains local. A controlled local evaluation
completed four trials on three selected routes without collisions; coordinate
alignment alone did not resolve the development-route collisions. These findings
do not establish dataset-wide superiority, learned-bridge benefits or real-time
execution. Third-party source, integration patches and raw evaluation artifacts
are outside the repository's distribution scope.
