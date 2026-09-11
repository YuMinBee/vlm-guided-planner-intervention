"""Planner-independent, capture-time navigation coordinates for VLM inputs."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple

Point = Tuple[float, float]


def _point(values: Iterable[float]) -> Point:
    point = tuple(float(value) for value in values)
    if len(point) != 2 or not all(math.isfinite(value) for value in point):
        raise ValueError('expected two finite coordinates')
    return point


@dataclass(frozen=True)
class NavigationSnapshot:
    """Local targets tied to the observation that supplied the camera image.

    Each target is (forward, right), in the same distance unit as the input.
    This snapshot does not validate a route or authorize a vehicle maneuver.
    """

    frame_id: int
    simulation_time_s: float
    near_forward_right: Point
    far_forward_right: Point

    def prompt_values(self) -> dict:
        near, far = self.near_forward_right, self.far_forward_right
        return {'coord_frame': 'ego_vehicle',
                'x_near': '%.3f' % near[0], 'y_near': '%.3f' % near[1],
                'x_far': '%.3f' % far[0], 'y_far': '%.3f' % far[1]}


def capture_navigation(*, frame_id: int, simulation_time_s: float,
                       position_xy: Iterable[float], forward_xy: Iterable[float],
                       right_xy: Iterable[float], near_target_xy: Iterable[float],
                       far_target_xy: Iterable[float]) -> NavigationSnapshot:
    """Project world displacements onto the captured ego forward/right axes.

    All inputs must use one world frame. Explicit orthonormal axes avoid
    assuming a simulator's compass origin, handedness or angle convention.
    Call before submitting a frame to the asynchronous worker, not when its
    delayed response arrives. The returned tuples retain no mutable inputs.
    """
    position, forward, right = map(_point, (position_xy, forward_xy, right_xy))
    targets = tuple(map(_point, (near_target_xy, far_target_xy)))
    if any(abs(sum(v*v for v in axis)-1.) > 1e-6 for axis in (forward, right)):
        raise ValueError('forward and right axes must have unit length')
    if abs(sum(a*b for a,b in zip(forward,right))) > 1e-6:
        raise ValueError('forward and right axes must be perpendicular')
    timestamp = float(simulation_time_s)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError('simulation_time_s must be finite and non-negative')
    if not isinstance(frame_id,int) or isinstance(frame_id,bool) or frame_id < 0:
        raise ValueError('frame_id must be a non-negative integer')
    converted = []
    for target in targets:
        delta = tuple(t-p for t,p in zip(target,position))
        converted.append(tuple(sum(d*a for d,a in zip(delta,axis)) for axis in (forward,right)))
    return NavigationSnapshot(frame_id, timestamp, converted[0], converted[1])
