# VLM-Guided Planner Intervention

> 상태: 동기식 로컬 프로토타입과 비동기 VLM 개입 주행의 검증 기록,
> 독립적 비동기 런타임 참조 구현, 압축된 성공·실패 시연 영상을 담습니다.
> 제3자 구현 코드나 원본 학습·평가 산출물은 포함하지 않습니다.

## 한 줄 아이디어

카메라 장면을 해석한 VLM의 고수준 주행 의도를 시간·경로·기하 조건으로
검증한 뒤, 기존 계획기의 후보 선택, 목표점 또는 제한된 궤적 보정에 반영한다.
연속 궤적 생성과 저수준 제어의 책임은 기존 계획기에 남긴다.

## 문제 정의

멀티모달 계획기는 여러 궤적 후보와 점수를 출력한다. 전체 점수가 가장 높은 후보가 경로 명령이나 장면의 의미와 항상 일치한다는 보장은 없다. 예를 들어 직진 의도가 분명한 상황에서도 좌회전 성향 후보가 선택될 수 있다.

목표점이나 명령 벡터를 입력에 추가하는 것만으로는 이 문제가 완전히 해결되지 않을 수 있다. 입력 조건은 바뀌어도 마지막 후보 선택 단계가 모든 모드를 다시 경쟁시키기 때문이다.

## 제안 구조

```mermaid
flowchart LR
    A[카메라 관측] --> B[VLM 고수준 의도 추론]
    A --> C[기존 궤적 계획기]
    B --> D[시간·경로 기반 명령 검증]
    C --> E[후보 궤적·점수·기본 목표점]
    D --> F[후보 제한·목표점 선택·제한 보정]
    E --> F
    F --> G[검증된 연속 궤적]
    G --> H[안전 폴백 및 제어]
```

핵심은 VLM이 직접 조향·가속 값을 생성하게 하지 않는다는 점이다. VLM은 `직진`, `좌회전`, `우회전`, `차선 변경`과 같은 고수준 제약만 제공하고, 연속 궤적과 저수준 제어는 기존 계획기의 영역으로 남긴다.

## 선택 규칙의 개요

기존 계획기가 후보 궤적 `T = {τ₁, …, τₙ}`과 점수 `sᵢ`를 만들고, VLM이 명령 `c`와 신뢰도 `q`를 출력한다고 하자.

1. 명령별 허용 집합 `A(c)`를 조회한다.
2. `A(c)` 밖의 후보를 최종 경쟁에서 제외한다.
3. 허용 후보에 대해 횡방향 이동, 종방향 진행, 곡률 등 간단한 기하 일관성을 검사한다.
4. 남은 후보 중 보정 점수가 가장 높은 궤적을 선택한다.
5. VLM 신뢰도가 낮거나 유효 후보가 없으면 사전에 정한 안전 폴백을 사용한다.

자세한 설계와 평가 계획은 [개념 문서](docs/concept.md)에 정리되어 있다.

## 비동기 런타임 실험

기존 계획기의 제어 주기가 VLM 추론을 기다리지 않도록, 크기 1의
최신 프레임 큐와 별도 worker를 두는 참조 런타임을 추가했다. 결과에는
원본 프레임과 시뮬레이션 시간을 붙이고, TTL을 넘거나 신뢰도가 낮은
명령은 폐기한다. 유효한 VLM 결과가 없으면 기존 계획기로 폴백한다.

- 설계: [비동기 런타임 문서](docs/async-runtime.md)
- CARLA 검증: [비동기 폴백 검증 기록](docs/async-validation.md)
- 독립 참조 구현: `src/vlm_async_gate/runtime.py`
- 모의 테스트: `PYTHONPATH=src python -m unittest discover -s tests -v`

독립 참조 구현은 모의 테스트를 통과했다. 같은 최신 결과·TTL·폴백
원칙을 로컬 통합 프로토타입에 적용한 CARLA 주행에서도 세 통제 경로를
완주했다. 범용 3B 모델 실험은 안전 폴백만 검증했지만, 후속 파인튜닝
7B 실험에서는 막힌 교차로의 51프레임 동안 VLM·route·유효 planner 명령이
`right`로 일치했고 검증된 우회전 target이 실제로 적용됐다. 열린 차량 문
회피 경로에서는 VLM의 `change_lane_left`가 60프레임 동안 인접 차선 target과
제한된 궤적 보정을 활성화했고, 충돌과 차선 이탈 없이 완주했다. 이는 비동기
개입 경로의 동작 증거이지만, native planner 대비 성능 향상을 입증하는 비교
실험은 아니다.

## 문 열림 시나리오 영상

동일한 Town13 `VehicleOpensDoorTwoWays` 경로에서 통합 설정을 수정하기 전의
실패 실행과 수정 후의 성공 실행을 함께 공개한다.

| 결과 | 영상 | 해석 |
|---|---|---|
| 성공 | [MP4 · 18.8초 · 6.8MB](media/demos/open-door-success.mp4) | VLM의 `change_lane_left`가 60프레임 동안 인접 차선 target과 제한 보정을 활성화해 충돌·이탈 없이 완주 |
| 실패 | [MP4 · 26.1초 · 9.2MB](media/demos/open-door-failure.mp4) | VLM은 열린 문과 좌측 변경을 인식했지만 이전 통합 설정에서 정체되어 31.99%에서 실행 중단 |

실패본은 VLM 인식 실패 비교군이 아니라 통합 설정의 실패를 보여 주는 진단
기록이다. 두 영상의 상세 조건과 제3자 출처는
[영상 설명과 출처](media/demos/README.md)에 정리했다.

## 로컬 프로토타입 검증

이 설계를 HiP-AD 기반의 로컬 연구 프로토타입에 연결해 두 개의 통제된
Bench2Drive 경로에서 확인했다. 두 실행 모두 카메라 프레임마다 로컬 VLM을
동기식으로 호출했으며, 미리 정한 명령 스케줄이나 강제 명령을 사용하지
않았다.

- `Town12/ParkingExit`: 경로 점수 100, 페널티 1.0, 종합 점수 100
- `Town12/BlockedIntersection`: 경로 점수 100, 페널티 1.0, 종합 점수 100
- 두 실행 모두 VLM 오류, 충돌, 경로 차선 이탈 0

교차로 실행에서는 VLM의 이른 회전 예측을 경로 명령과 일치할 때까지
보류하고, 일치한 구간에서만 CARLA 지도 분기를 목표점으로 사용했다. 상세한
조건, 집계 수치, 한계는 [검증 기록](docs/verified-prototype.md)에 적었다.

## 설계 이유

- 고수준 의미 판단과 연속 제어를 분리해 VLM의 불안정성이 차량 제어에 직접 전달되는 것을 줄인다.
- 기존 계획기를 다시 학습하지 않고도 후보 선택 단계에 결합할 수 있다.
- 명령별 후보 수를 제한해 의미적으로 잘못된 모드가 높은 점수만으로 선택되는 문제를 줄인다.
- 명목상 모드 그룹과 실제 궤적 형태가 다를 수 있으므로, 고정된 인덱스 이름을 맹신하지 않고 오프라인 보정과 기하 검증을 함께 사용한다.

## 이 저장소에 포함하지 않는 것

이 저장소는 아이디어의 독립적인 설명과 제3자 프로젝트에 의존하지
않는 최소 참조 구현만 담는다. 다음 자료는 포함하지 않는다.

- HiP-AD 또는 다른 제3자 프로젝트의 소스 코드와 설정 파일
- 모델 가중치, 데이터셋, 원본 이미지·영상, 논문 그림
- 제3자 저장소에서 생성된 원본 로그와 평가 산출물
- HiP-AD 또는 다른 제3자 파일을 수정한 패치와 통합 코드

예외적으로 이 저장소가 직접 기록·압축한 문 열림 시나리오 시연 영상 두 개만
포함하며, 영상에 보이는 제3자 시뮬레이터 에셋의 권리는 원 권리자에게 있다.

## 배경 참고

이 아이디어를 검토한 배경 시스템 중 하나는 [HiP-AD](https://github.com/nullmax-vision/HiP-AD)이다. HiP-AD는 해당 프로젝트 저작자의 저작물이며, 이 저장소는 HiP-AD 공식 프로젝트가 아니고 제휴 관계도 없다. 본 저장소에는 HiP-AD의 코드를 복사하지 않았다. 세부 경계는 [제3자 자료 정책](THIRD_PARTY.md)을 참고한다.

## 공개 및 권리 상태

현재 별도 오픈소스 라이선스를 부여하지 않는다. 저장소 내용에 대한 사용 허가는 [RIGHTS.md](RIGHTS.md)를 따른다. 공개 전에는 [공개 체크리스트](docs/publication-checklist.md)를 검토해야 한다.

## English summary

This repository documents a model-agnostic planner-intervention concept,
aggregate observations from synchronous and asynchronous local prototypes,
an independent asynchronous latest-frame runtime reference, and two compressed
open-door demonstration recordings. A vision-language model supplies validated
high-level intent while the base planner retains continuous trajectory and
control responsibility. The repository contains no third-party source code,
weights, datasets, figures, raw logs, original evaluation artifacts, or planner
integration patches.
