# 관측 시점의 차량 기준 좌표

VLM 프롬프트에 `ego_vehicle`, x=전방, y=우측이라고 적었다면 목표점도
그 좌표계로 변환해야 한다. 지도상의 절대 위치를 그대로 넣으면 먼 세계
좌표가 차량 바로 앞의 이동량으로 해석될 수 있다.

독립 참조 함수 `capture_navigation`은 같은 세계 좌표계의 현재 위치와
목표점 차이를 차량의 전방·우측 단위축에 투영한다. 지도 원점과 센서별
방향각 규약을 고정하지 않으므로, 호출자가 자신의 좌표계에 맞는 두 축을
제공해야 한다. 단위는 입력 좌표와 같으며 주행 프롬프트에는 미터를 사용한다.

```python
from vlm_async_gate import FrameSample, capture_navigation

navigation = capture_navigation(
    frame_id=10, simulation_time_s=1.0,
    position_xy=(100, 200),
    forward_xy=(0, -1), right_xy=(1, 0),
    near_target_xy=(102, 190), far_target_xy=(97, 180),
)
assert navigation.near_forward_right == (10.0, 2.0)
prompt_fields = navigation.prompt_values()
sample = FrameSample(navigation.frame_id, navigation.simulation_time_s, navigation)
# worker.submit(sample): 실제 입력에는 같은 시점의 카메라 관측도 함께 묶는다.
```

변환은 카메라 관측을 큐에 넣기 전에 한다. 비동기 응답을 받는 시점의 새
차량 위치로 과거 관측을 다시 해석하지 않는다. 함수가 반환한 좌표는
불변 튜플이므로 호출자가 원래 위치 배열을 수정해도 바뀌지 않는다.
응답 수용 여부는 별도로 기존 런타임의 TTL·신뢰도 조건에서 판단한다.

원점 이동, 회전, 전방/우측 성분, 잘못된 축, 지연 worker의 관측 보존을
테스트한다. 이 참조 함수는 특정 계획기 API나 통합 패치를 포함하지 않는다.
로컬 HiP-AD 통합에서는 해당 프로젝트의 좌표 관례를 맞추는 별도 수정이
필요하며, 이 함수를 추가했다는 사실만으로 그 통합이 자동 적용되지는 않는다.

좌표 오류 수정만으로 충돌이 해결된 것은 아니다. 이후의 제어 구성과 결과는
[추가 검증 기록](grounded-control-validation.md)에 별도로 정리한다.
