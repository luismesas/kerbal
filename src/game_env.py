import math
import time

import pandas as pd
import numpy as np

from krpc_helper import KRPCHelper
from logger import Logger


class GameEnv(object):
    def __init__(self, logger: Logger, krpc: KRPCHelper, saved_game_name: str):
        self.logger: Logger = logger
        self.krpc: KRPCHelper = krpc
        self.saved_game_name = saved_game_name

        self.total_steps: int = 0

        self.action_space: int = 2
        self.observation_space: int = 3
        self.observation_space: int = 4

        self.last_altitude: float = 0
        self.last_pitch: float = 0
        self.last_heading: float = 0
        self.max_altitude: float = 45000
        self.last_roll: float = 0
        self.steps_limit: int = 450

        self.ground_truth = pd.read_csv("artifacts/groundtruth.csv")

    def step(self, action):
        done = False

        self.total_steps += 1

        # _old_time = time.time()

        # self.krpc.reset_controls()

        # print(f"elapsed_time_C-1[{time.time()-_old_time}]")
        # _old_time = time.time()

        self.choose_action(action)
        # print(f"self.choose_action(action) > [{time.time()-_old_time}]")
        # _old_time = time.time()
        state = self.get_state()
        # print(f"state = self.get_state() > [{time.time()-_old_time}]")
        # _old_time = time.time()
        reward = self.get_reward()
        # print(f"reward = self.get_reward() > [{time.time()-_old_time}]")
        # _old_time = time.time()
        done = self.epoch_ending()
        # print(f"done = self.epoch_ending() > [{time.time()-_old_time}]")
        # _old_time = time.time()

        return state, reward, done, {}

    def choose_action(self, action):
        if action == 0:
            pass
        elif action == 1:
            self.krpc.vessel.control.pitch += -0.1
        elif action == 2:
            self.krpc.vessel.control.pitch += 0.1
        elif action == 3:
            self.krpc.vessel.control.yaw += -0.1
        elif action == 4:
            self.krpc.vessel.control.yaw += 0.1
        elif action == 5:
            self.krpc.vessel.control.roll += -0.1
        elif action == 6:
            self.krpc.vessel.control.roll += 0.1

    def epoch_ending(self):
        telemetry = self.krpc.get_telemetry()
        altitude = telemetry.f_mean_altitude
        crew_count = telemetry.crew_count()

        done = False
        if crew_count == 0:
            done = True
        elif self.total_steps > self.steps_limit:
            done = True
        elif altitude >= self.max_altitude:
            done = True
        elif self.last_altitude < 10000 and self.last_pitch < 0:
            done = True

        return done

    def get_reward(self):
        # Calculate the rewards related to GroundTruth - Altitude
        gt_altitude = self.ground_truth['altitude'].values[self.total_steps]
        altitude_rewards = (gt_altitude - self.last_altitude) / gt_altitude
        altitude_rewards = np.abs(altitude_rewards)

        # Calcultae the rewards related to GroundTruth - Pitch
        gt_pitch = self.ground_truth['pitch'].values[self.total_steps]
        pitch_rewards = (gt_pitch - self.last_pitch) / gt_pitch
        pitch_rewards = np.abs(pitch_rewards)

        reward = (0.5 * altitude_rewards) + (0.5 * pitch_rewards)
        reward = -reward

        return reward

    def reset(self):
        self.krpc.load_game(self.saved_game_name)
        self.pre_launch_setup()
        self.activate_engine()

        self.last_altitude = 0
        self.last_pitch = 0
        self.last_heading = 0
        self.total_steps = 0
        state = self.get_state()

        return state

    def get_state(self):
        telemetry = self.krpc.get_telemetry()

        altitude = telemetry.f_mean_altitude
        heading = telemetry.heading()
        pitch = telemetry.pitch()
        roll = telemetry.roll()

        state = [
            ((altitude + 0.2) / self.max_altitude) / 1.2,
            math.sin(math.radians(heading)) * (90 - pitch) / 90,
            math.cos(math.radians(heading)) * (90 - pitch) / 90,
            roll/180,
        ]

        self.last_altitude = altitude
        self.last_pitch = pitch
        self.last_roll = roll

        return state

    def pre_launch_setup(self):
        self.krpc.vessel.control.sas = False
        self.krpc.vessel.control.rcs = False

        self.altitude_max = 0
        self.counter = 0
        self.prev_pitch = 90

    def activate_engine(self, throttle=1.0):
        self.krpc.vessel.control.throttle = throttle
        self.krpc.vessel.control.activate_next_stage()
        time.sleep(2)
