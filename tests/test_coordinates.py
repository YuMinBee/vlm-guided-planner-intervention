import math
import threading
import unittest

from vlm_async_gate import FrameSample, LatestFrameWorker, capture_navigation


class NavigationCoordinatesTest(unittest.TestCase):
    def capture(self, **changes):
        arguments = dict(frame_id=10, simulation_time_s=1., position_xy=[100.,200.],
            forward_xy=[0.,-1.], right_xy=[1.,0.], near_target_xy=[102.,190.],far_target_xy=[97.,180.])
        arguments.update(changes)
        return capture_navigation(**arguments)

    def test_absolute_location_becomes_local_forward_right(self):
        snapshot = self.capture()
        self.assertEqual(snapshot.near_forward_right, (10.,2.))
        self.assertEqual(snapshot.far_forward_right, (20.,-3.))
        self.assertEqual(snapshot.prompt_values(), dict(coord_frame='ego_vehicle',
            x_near='10.000',y_near='2.000',x_far='20.000',y_far='-3.000'))

    def test_world_origin_does_not_change_local_target(self):
        a=self.capture()
        b=self.capture(position_xy=[0.,0.],near_target_xy=[2.,-10.],far_target_xy=[-3.,-20.])
        self.assertEqual(a.near_forward_right,b.near_forward_right)
        self.assertEqual(a.far_forward_right,b.far_forward_right)

    def test_rotating_world_axes_preserves_ego_geometry(self):
        for angle in [0.,math.pi/2,math.pi,-math.pi/2,.7]:
            forward=[math.cos(angle),math.sin(angle)]
            right=[math.sin(angle),-math.cos(angle)]
            target=[100+12*forward[0]-3*right[0],200+12*forward[1]-3*right[1]]
            result=self.capture(forward_xy=forward,right_xy=right,near_target_xy=target)
            self.assertAlmostEqual(result.near_forward_right[0],12.)
            self.assertAlmostEqual(result.near_forward_right[1],-3.)

    def test_invalid_basis_and_observation_rejected(self):
        for changes in [dict(forward_xy=[0.,2.]),dict(right_xy=[0.,-1.]),
                        dict(position_xy=[math.nan,0.]),dict(simulation_time_s=math.inf),
                        dict(frame_id=-1),dict(frame_id=True)]:
            with self.assertRaises(ValueError):self.capture(**changes)

    def test_delayed_worker_keeps_capture_time_coordinates(self):
        position=[100.,200.];target=[102.,190.]
        snapshot=self.capture(position_xy=position,near_target_xy=target)
        started=threading.Event();release=threading.Event();done=threading.Event();seen=[]
        def infer(payload):
            started.set();release.wait(1.)
            seen.append(payload.prompt_values());done.set()
            return 'right',.9
        worker=LatestFrameWorker(infer,allowed_commands=['right']);worker.start()
        try:
            worker.submit(FrameSample(snapshot.frame_id,snapshot.simulation_time_s,snapshot))
            self.assertTrue(started.wait(1.))
            position[:]=[1000.,2000.];target[:]=[0.,0.]
            release.set();self.assertTrue(done.wait(1.))
            self.assertEqual(seen[0]['x_near'],'10.000')
            self.assertEqual(seen[0]['y_near'],'2.000')
        finally:
            release.set();self.assertTrue(worker.close())


if __name__=='__main__':unittest.main()
