# VLM-Guided Semantic Trajectory Gating

> 상태: 개인 연구 아이디어 문서. 구현 코드나 학습 산출물을 배포하는 저장소가 아닙니다.

## 한 줄 아이디어

카메라 장면을 해석한 VLM의 고수준 주행 의도를 이용해, 기존 멀티모달 궤적 계획기가 만든 후보 중 **의미적으로 허용되는 후보 집합을 먼저 한정**한 뒤 그 안에서 최종 궤적을 선택한다.

## 문제 정의

멀티모달 계획기는 여러 궤적 후보와 점수를 출력한다. 전체 점수가 가장 높은 후보가 경로 명령이나 장면의 의미와 항상 일치한다는 보장은 없다. 예를 들어 직진 의도가 분명한 상황에서도 좌회전 성향 후보가 선택될 수 있다.

목표점이나 명령 벡터를 입력에 추가하는 것만으로는 이 문제가 완전히 해결되지 않을 수 있다. 입력 조건은 바뀌어도 마지막 후보 선택 단계가 모든 모드를 다시 경쟁시키기 때문이다.

## 제안 구조

```mermaid
flowchart LR
    A[카메라 관측] --> B[VLM 고수준 의도 추론]
    A --> C[기존 궤적 계획기]
    B --> D[명령별 허용 후보 집합]
    C --> E[후보 궤적과 점수]
    D --> F[의미 마스킹 및 기하 검증]
    E --> F
    F --> G[허용 집합 내 최종 선택]
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

## 설계 이유

- 고수준 의미 판단과 연속 제어를 분리해 VLM의 불안정성이 차량 제어에 직접 전달되는 것을 줄인다.
- 기존 계획기를 다시 학습하지 않고도 후보 선택 단계에 결합할 수 있다.
- 명령별 후보 수를 제한해 의미적으로 잘못된 모드가 높은 점수만으로 선택되는 문제를 줄인다.
- 명목상 모드 그룹과 실제 궤적 형태가 다를 수 있으므로, 고정된 인덱스 이름을 맹신하지 않고 오프라인 보정과 기하 검증을 함께 사용한다.

## 이 저장소에 포함하지 않는 것

이 저장소는 아이디어의 독립적인 설명만 담는다. 다음 자료는 포함하지 않는다.

- HiP-AD 또는 다른 제3자 프로젝트의 소스 코드와 설정 파일
- 모델 가중치, 데이터셋, 이미지, 동영상, 논문 그림
- 제3자 저장소에서 생성된 로그와 평가 산출물
- 기존 파일을 수정한 패치나 재배포 가능한 실행 구현

## 배경 참고

이 아이디어를 검토한 배경 시스템 중 하나는 [HiP-AD](https://github.com/nullmax-vision/HiP-AD)이다. HiP-AD는 해당 프로젝트 저작자의 저작물이며, 이 저장소는 HiP-AD 공식 프로젝트가 아니고 제휴 관계도 없다. 본 저장소에는 HiP-AD의 코드를 복사하지 않았다. 세부 경계는 [제3자 자료 정책](THIRD_PARTY.md)을 참고한다.

## 공개 및 권리 상태

현재 별도 오픈소스 라이선스를 부여하지 않는다. 저장소 내용에 대한 사용 허가는 [RIGHTS.md](RIGHTS.md)를 따른다. 공개 전에는 [공개 체크리스트](docs/publication-checklist.md)를 검토해야 한다.

## English summary

This repository documents a model-agnostic concept: use a vision-language model to infer a high-level driving intent, restrict a multimodal motion planner to a command-consistent candidate set, apply lightweight geometric consistency checks, and select the final trajectory with an explicit safety fallback. It contains no third-party source code, weights, datasets, figures, or evaluation artifacts.
