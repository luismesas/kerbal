# Adapted from https://github.com/under-control/flytosky/blob/master/ksp_env.py
import math
import time

import numpy as np

from gym import spaces


class GameEnv(object):
    def __init__(self, conn, max_alt=45000):
        self.set_telemetry(conn)
        self.pre_launch_setup()
        self.max_alt = max_alt

        # low and high values for each action (pitch, roll, yaw)
        action_low = np.array([-1, -1, -1, 0])
        action_high = np.array([1, 1, 1, 1])
        self.action_space = spaces.Box(action_low, action_high, dtype=np.float32)

        low = np.array([0, -1, -1])
        high = np.array([1, 1, 1])
        self.observation_space = spaces.Box(low, high, dtype=np.float32)

    def set_telemetry(self, conn):
        self.conn = conn
        self.vessel = conn.space_center.active_vessel

        # Setting up streams for telemetry
        self.altitude = conn.add_stream(getattr, self.vessel.flight(), 'mean_altitude')
        self.apoapsis = conn.add_stream(getattr, self.vessel.orbit, 'apoapsis_altitude')
        self.crew = conn.add_stream(getattr, self.vessel, 'crew_count')
        self.frame = self.vessel.orbit.body.reference_frame
        self.g_force = conn.add_stream(getattr, self.vessel.flight(), 'g_force')
        self.heading = conn.add_stream(getattr, self.vessel.flight(), 'heading')
        self.lift = conn.add_stream(getattr, self.vessel.flight(), 'lift')
        self.periapsis = conn.add_stream(getattr, self.vessel.orbit, 'periapsis_altitude')
        self.parts = conn.add_stream(getattr, self.vessel.parts, 'all')
        self.pitch = conn.add_stream(getattr, self.vessel.flight(), 'pitch')
        self.roll = conn.add_stream(getattr, self.vessel.flight(), 'roll')
        self.speed = conn.add_stream(getattr, self.vessel.flight(), 'velocity')
        self.stage_2_resources = self.vessel.resources_in_decouple_stage(stage=2, cumulative=False)
        self.srb_fuel = conn.add_stream(self.stage_2_resources.amount, 'SolidFuel')
        self.ut = conn.add_stream(getattr, conn.space_center, 'ut')
        self.vert_speed = conn.add_stream(getattr, self.vessel.flight(self.frame), 'vertical_speed')

    def pre_launch_setup(self):
        self.vessel.control.sas = False
        self.vessel.control.rcs = False

        self.altitude_max = 0
        self.counter = 0
        self.prev_pitch = 90

    def step(self, action):
        """
        possible continuous actions: yaw[-1:1], pitch[-1:1], roll[-1:1], throttle[0:1],
        other: forward[-1:1], up[-1:1], right[-1:1], wheel_throttle[-1:1], wheel_steering[-1:1],
        available observation
        https://krpc.github.io/krpc/python/api/space-center/control.html
        available states:
        https://krpc.github.io/krpc/python/api/space-center/flight.html
        https://krpc.github.io/krpc/python/api/space-center/orbit.html
        https://krpc.github.io/krpc/python/api/space-center/reference-frame.html
        :param action:
        :return state, reward, done, {}:
        """
        done = False

        # self.conn.ui.message(str(action), duration=1.5)

        start_act = self.ut()
        
        self.vessel.control.pitch = 0
        self.vessel.control.yaw = 0
        self.vessel.control.roll = 0
        self.choose_action(action)

        # 10 actions in one second in game time
        while self.ut() - start_act <= 0.1:
            continue

        state = self.get_state()
        # self.conn.ui.message("State: " + str(state), duration=1.5)

        reward = self.turn_reward()
        reward, done = self.epoch_ending(reward, done)
        # self.conn.ui.message("Reward: " + str(round(reward, 2)), duration=1.5)

        self.counter += 1

        if done:
            self.counter = 0

        if self.altitude() > self.altitude_max:
            self.altitude_max = self.altitude()

        return state, reward, done, {}

    def choose_action(self, action):
        if action == 0:  # do nothing action, wait
            pass
        elif action == 1:
            self.vessel.control.pitch = -1
        elif action == 2:
            self.vessel.control.pitch = 1
        elif action == 3:
            self.vessel.control.roll = -1
        elif action == 4:
            self.vessel.control.roll = 1
        elif action == 5:
            self.vessel.control.yaw = -1
        elif action == 6:
            self.vessel.control.yaw = 1
        elif action == 7:
            self.vessel.control.throttle = 0
        elif action == 8:
            self.vessel.control.throttle = 1

    def epoch_ending(self, reward, done):
        if self.altitude() >= self.max_alt:
            reward = 1
            done = True
            print('reached max altitude at: ', self.altitude(), end=' | ')
        elif self.crew() == 0:
            reward = -1
            done = True
            print('crew is dead :(')
        else:
            reward = -1

        return reward, done

    def reset(self, conn):
        """
        revivekerbals is a quick save file and should be in /GOG/KSP/game/saves/kill
        to run the code you will need to download it from
        https://drive.google.com/file/d/1L1DdeUdHpcMSmO8royVWocitVR93UwdE
        :param conn: krpc.connection
        :return: state
        """
        self.altitude_max = 0
        quick_save = "revivekerbals"

        try:
            self.conn.space_center.load(quick_save)
        except Exception as ex:
            print("Error:", ex)
            print("Add \"kill\" save to your saves directory")
            exit("You have no quick save named {}. Terminating.".format(quick_save))

        time.sleep(3)

        self.set_telemetry(conn)  # game is reloaded and we need to reset the telemetry
        self.pre_launch_setup()
        self.conn.space_center.physics_warp_factor = 0
        state = self.get_state()

        self.activate_engine()

        return state

    def get_state(self):
        state = [
            ((self.altitude() + 0.2) / self.max_alt) / 1.2,
            math.sin(math.radians(self.heading())) * (90 - self.pitch()) / 90,
            math.cos(math.radians(self.heading())) * (90 - self.pitch()) / 90,
        ]

        return state

    def _normalize(self, feature):
        return 1 / (1 + round(math.pow(math.e, -feature), 5))

    def difference(self, turn_start_altitude=250, turn_end_altitude=45000):
        fractal = (self.altitude() - turn_start_altitude) \
                  / (turn_end_altitude - turn_start_altitude)
        turn_angle = 90 - fractal * 90
        deviation = abs(turn_angle - self.pitch())

        return deviation

    def turn_reward(self):
        reward = 0
        if str(self.vessel.situation) == "VesselSituation.flying":
            deviation = self.difference()
            if deviation < 10:
                reward = 1
            else:
                reward = -1

            self.prev_pitch = self.pitch()

        return reward

    def activate_engine(self, throttle=1.0):
        self.vessel.control.throttle = throttle
        self.vessel.control.activate_next_stage()
        time.sleep(2)

    def get_altitude(self):
        return round(self.altitude_max, 2)