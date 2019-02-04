# This file is part of ts_ATDome.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

import asyncio
import math
import unittest

from lsst.ts import salobj
from lsst.ts import ATDome

import SALPY_ATDome

port_generator = salobj.index_generator(imin=3200)


class Harness:
    def __init__(self, initial_state):
        salobj.test_utils.set_random_lsst_dds_domain()
        self.port = next(port_generator)
        self.index = 1
        self.remote = salobj.Remote(SALPY_ATDome, index=self.index)
        self.csc = ATDome.ATDomeCsc(
            index=self.index, port=self.port,
            initial_state=initial_state, initial_simulation_mode=1)

    async def stop(self):
        await asyncio.wait_for(self.csc.stop(), timeout=2)


class CscTestCase(unittest.TestCase):
    def test_initial_info(self):

        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=5)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)

            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=2)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_NotInMotionState)

            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state, SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            emergency_stop = await harness.remote.evt_emergencyStop.next(flush=False, timeout=2)
            self.assertFalse(emergency_stop.active)

            position = await harness.remote.tel_position.next(flush=False, timeout=2)
            self.assertEqual(position.dropoutOpeningPercentage, 0)
            self.assertEqual(position.mainDoorOpeningPercentage, 0)
            self.assertAlmostEqual(position.azimuthPosition, 0)
            self.assertTrue(math.isnan(position.dropoutOpeningPercentageSet))
            self.assertTrue(math.isnan(position.mainDoorOpeningPercentageSet))
            self.assertTrue(math.isnan(position.azimuthPositionSet))

            await harness.stop()

        asyncio.get_event_loop().run_until_complete(doit())

    def test_move_az(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=5)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=2)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_NotInMotionState)

            desired_azimuth = 354
            harness.remote.cmd_moveAzimuth.set(azimuth=desired_azimuth)
            await harness.remote.cmd_moveAzimuth.start(timeout=2)

            # wait for the move to begin and check status
            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=1)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_MovingCCWState)
            position = harness.remote.tel_position.get()
            self.assertAlmostEqual(position.azimuthPositionSet, desired_azimuth)
            self.assertGreater(position.azimuthPosition, desired_azimuth)
            self.assertLess(position.azimuthPosition, 360)

            # wait for the move to end and check status
            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=1)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_NotInMotionState)
            position = harness.remote.tel_position.get()
            self.assertAlmostEqual(position.azimuthPositionSet, desired_azimuth)
            self.assertAlmostEqual(position.azimuthPosition, desired_azimuth)

            # try several invalid values for azimuth
            for bad_az in (-0.001, 360.001):
                harness.remote.cmd_moveAzimuth.set(azimuth=bad_az)
                with salobj.test_utils.assertRaisesAckError():
                    await harness.remote.cmd_moveAzimuth.start(timeout=2)

            await harness.stop()

        asyncio.get_event_loop().run_until_complete(doit())

    def test_move_shutter(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=5)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)

            # open both doors
            await harness.remote.cmd_openShutter.start(timeout=2)

            # wait for the move to begin and check status
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=1)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpeningState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=1)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpeningState)
            shutter_in_pos = await harness.remote.evt_shutterInPosition.next(flush=False, timeout=1)
            self.assertFalse(shutter_in_pos.inPosition)

            # wait for the move to end and check status
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpenedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpenedState)
            shutter_in_pos = await harness.remote.evt_shutterInPosition.next(flush=False, timeout=2)
            self.assertTrue(shutter_in_pos.inPosition)

            # close both doors
            await harness.remote.cmd_closeShutter.start(timeout=2)

            # wait for the move to begin and check status
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=1)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosingState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=1)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosingState)
            shutter_in_pos = await harness.remote.evt_shutterInPosition.next(flush=False, timeout=1)
            self.assertFalse(shutter_in_pos.inPosition)

            # wait for the move to end and check status
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            shutter_in_pos = await harness.remote.evt_shutterInPosition.next(flush=False, timeout=2)
            self.assertTrue(shutter_in_pos.inPosition)

            await harness.stop()

        asyncio.get_event_loop().run_until_complete(doit())

    def test_stop(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=5)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=1)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_NotInMotionState)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_ClosedState)

            # move azimuth and open both doors
            harness.remote.cmd_moveAzimuth.set(azimuth=354)
            await harness.remote.cmd_moveAzimuth.start(timeout=2)
            await harness.remote.cmd_openShutter.start(timeout=2)

            # wait for the moves to start
            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=1)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_MovingCCWState)
            az_in_position = await harness.remote.evt_azimuthInPosition.next(flush=False, timeout=1)
            self.assertFalse(az_in_position.inPosition)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpeningState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_OpeningState)
            shutter_in_pos = await harness.remote.evt_shutterInPosition.next(flush=False, timeout=1)
            self.assertFalse(shutter_in_pos.inPosition)

            # stop all motion
            # this should not produce new "inPosition" events, because
            # motion is stopped while the axes are still not in position
            await harness.remote.cmd_stopMotion.start(timeout=2)

            az_state = await harness.remote.evt_azimuthState.next(flush=False, timeout=1)
            self.assertEqual(az_state.state, SALPY_ATDome.ATDome_shared_AzimuthState_NotInMotionState)
            with self.assertRaises(asyncio.TimeoutError):
                await harness.remote.evt_azimuthInPosition.next(flush=False, timeout=0.1)
            main_door_state = await harness.remote.evt_mainDoorState.next(flush=False, timeout=2)
            self.assertEqual(main_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_PartiallyOpenedState)
            dropout_door_state = await harness.remote.evt_dropoutDoorState.next(flush=False, timeout=2)
            self.assertEqual(dropout_door_state.state,
                             SALPY_ATDome.ATDome_shared_ShutterDoorState_PartiallyOpenedState)
            with self.assertRaises(asyncio.TimeoutError):
                await harness.remote.evt_shutterInPosition.next(flush=False, timeout=0.1)

            await harness.stop()

        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
