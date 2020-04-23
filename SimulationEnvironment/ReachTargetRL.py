from rlbench.environment import Environment
from rlbench.action_modes import ArmActionMode, ActionMode
from rlbench.observation_config import ObservationConfig
from rlbench.backend.observation import Observation
from rlbench.tasks import ReachTarget
from typing import List
from quaternion import from_rotation_matrix, quaternion
import scipy as sp
import numpy as np
from gym import spaces
from .Environment import SimulationEnvironment
from .Environment import image_types,DEFAULT_ACTION_MODE,ArmActionMode

import sys
sys.path.append('..')
from models.Agent import LearningAgent,RLAgent
import logger

class ReplayBuffer():
    
    def __init__(self):
        self.observations = []
        self.rewards = []
        self.actions = []
        self.total_reward = 0

    def store(self,observation:Observation,action,reward:int):
        self.observation.append(observation)
        self.actions.append(action)
        self.observation.append(reward)

DEFAULT_ACTION_MODE = ActionMode(ArmActionMode.ABS_JOINT_VELOCITY)
DEFAULT_TASK = ReachTarget

class ReachTargetRLEnvironment(SimulationEnvironment):
    
    def __init__(self, 
                action_mode=DEFAULT_ACTION_MODE,\
                task=DEFAULT_TASK,\
                headless=True,
                num_episodes=100, 
                episode_length=15, 
                dataset_root=''):

        super(ReachTargetRLEnvironment,self).__init__(action_mode=action_mode, task=ReachTarget, headless=headless,dataset_root=dataset_root)
        # training parameters
        self.num_episodes = num_episodes
        self.episode_length = episode_length
        self.logger = logger.create_logger(__class__.__name__)
        self.logger.propagate = 0

  

    def reward_function(self, state:Observation, action, rl_bench_reward):
        """
        reward_function : Reward function for non Sparse Rewards. 
        Input Parameters
        ---------- 
        state : state observation.
        action: action taken  by the agent in case needed for reward shaping=
        """
       
        return rl_bench_reward
    #IMP
    def _get_state(self, obs:Observation,check_images=True):
        # _get_state function is present so that some alterations can be made to observations so that
        # dimensionality management is handled from lower level. 

        if not check_images: # This is set so that image loading can be avoided
            return obs

        for state_type in image_types:    # changing axis of images in `Observation`
            image = getattr(obs, state_type)
            if image is None:
                continue
            if len(image.shape) == 2:
                # Depth and Mask can be single channel.Hence we Reshape the image from (width,height) -> (width,height,1)
                image = image.reshape(*image.shape,1)
            # self.logger.info("Shape of : %s Before Move Axis %s" % (state_type,str(image.shape)))
            image=np.moveaxis(image, 2, 0)  # change (H, W, C) to (C, H, W) for torch
            # self.logger.info("After Moveaxis :: %s" % str(image.shape))
            setattr(obs,state_type,image)

        return obs
   
    
    #IMP
    def step(self, action):
        error = None
        state_obs = None
        obs_, reward, terminate = self.task.step(action)  # reward in original rlbench is binary for success or not
        print("Got Step ")
        state_obs = self._get_state(obs_)
        shaped_reward = self.reward_function(state_obs,action,reward)
        return state_obs, shaped_reward, terminate

    # IMP
    def train_rl_agent(self,agent:RLAgent):
        replay_buffer = ReplayBuffer()
        total_steps = 0 # Total Steps of all Episodes.
        valid_steps = 0 # Valid steps predicted by the agent

        for episode_i in range(self.num_episodes):
            descriptions, obs = self.task.reset()
            prev_obs = obs
            agent.reset([self._get_state(obs)]) # Reset to Rescue for resetting s_t in agent on failure
            step_counter = 0 # A counter of valid_steps within episiode
            useless_step_counter = 0 # Total steps within episode include bullshit path plans

            while step_counter < self.episode_length:
            # for step_counter in range(self.episode_length): # Iterate for each timestep in Episode length
                total_steps+=1
                useless_step_counter+=1
                action = agent.act([prev_obs],timestep=step_counter) # Provide state s_t to agent.
                selected_action = action
                print("Step Counter",step_counter,agent.warmup)
                print(action)
                # try:
                new_obs, reward, terminate = self.step(selected_action)
                self.logger.info("Found Path And Got Reward : %d " % reward)
                step_counter+=1
                valid_steps+=1
                # except Exception as e:
                #     print(e)
                #     if useless_step_counter > 20:
                #         break
                #     continue
                
                if step_counter == self.episode_length-1:
                    terminate = True # setting termination here becuase failed trajectory. 
                # ! In case of failure the step function will return NONE
                # ! The agent will have to handle None state as reward and terminate are passed.
                elif reward > 100:
                    terminate = True # end the episode early if the objective is acheived

                agent.observe([new_obs],action,reward,terminate) # s_t+1,a_t,reward_t : This should also be thought out.
                prev_obs = new_obs
                replay_buffer.total_reward+=reward
                if valid_steps > agent.warmup:
                    agent.update()
                if terminate:
                    self.logger.info("Terminating!!")
                    break
                if useless_step_counter > 20: # if the agent 
                    break
            self.logger.info("Total Reward Gain For all Epsiodes : %d"%replay_buffer.total_reward)
