import gym, sys
import numpy, random
import utils_for_q_learning, buffer_class

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy
import pickle
from collections import deque

if torch.cuda.is_available():
	device = torch.device("cuda:0")
	print("Running on the GPU")
else:
	device = torch.device("cpu")
	print("Running on the CPU")

LOGGING_LEVEL = 1

def _print(logging_level, stuff):
	if LOGGING_LEVEL >= logging_level:
		print(stuff)


def rbf_function_single_batch_mode(centroid_locations, beta, N, norm_smoothing):
	'''
		no batch
		given N centroids * size of each centroid
		determine weight of each centroid at each other centroid
	'''
	_print(2, "rbf_function_single_batch_mode: centroid locations length {} and shape of elems {}".format(len(centroid_locations), centroid_locations[0].shape))
	centroid_locations = [c.unsqueeze(1) for c in centroid_locations]
	centroid_locations_cat = torch.cat(centroid_locations, dim=1)
	centroid_locations_cat = centroid_locations_cat.unsqueeze(2)
	centroid_locations_cat = torch.cat([centroid_locations_cat for _ in range(N)],dim=2)
	centroid_locations_cat_transpose = centroid_locations_cat.permute(0,2,1,3)
	diff      = centroid_locations_cat - centroid_locations_cat_transpose
	diff_norm = diff**2
	diff_norm = torch.sum(diff_norm, dim=3)
	diff_norm = diff_norm + norm_smoothing
	diff_norm = torch.sqrt(diff_norm)
	diff_norm = diff_norm * beta * -1
	weights   = F.softmax(diff_norm, dim=2)

	_print(2, "rbf_function_single_batch_mode: weights shape: {}".format(weights.shape))

	return weights

def new_rbf_function_single_batch_mode(centroid_locations, beta, N, norm_smoothing):
	'''
		no batch
		now, centroid_locations is a tensor! 

		given N centroids * size of each centroid
		determine weight of each centroid at each other centroid

		Essentially we're making a distance-from-to thing
		The tough thing here, as always,  

	'''
	centroid_locations = [c.unsqueeze(1) for c in centroid_locations]
	centroid_locations_cat = torch.cat(centroid_locations, dim=1)
	centroid_locations_cat = centroid_locations_cat.unsqueeze(2)
	centroid_locations_cat = torch.cat([centroid_locations_cat for _ in range(N)],dim=2) # [num_states (1), num_centroids, num_centroids, action_dim]
	centroid_locations_cat_transpose = centroid_locations_cat.permute(0,2,1,3) # [num_states (1), num_centroids, num_centroids, action_dim]
	diff      = centroid_locations_cat - centroid_locations_cat_transpose
	diff_norm = diff**2
	diff_norm = torch.sum(diff_norm, dim=3)
	diff_norm = diff_norm + norm_smoothing
	diff_norm = torch.sqrt(diff_norm)
	diff_norm = diff_norm * beta * -1
	weights   = F.softmax(diff_norm, dim=2)
	return weights

def rbf_function(centroid_locations, action, beta, N, norm_smoothing):
	'''
		given batch size * N centroids * size of each centroid
		and batch size * size of each action, determine the weight of
		each centroid for the action 
	'''
	centroid_locations_squeezed = [l.unsqueeze(1) for l in centroid_locations]
	centroid_locations_cat = torch.cat(centroid_locations_squeezed, dim=1)
	action_unsqueezed = action.unsqueeze(1)
	action_cat = torch.cat([action_unsqueezed for _ in range(N)], dim=1)
	diff = centroid_locations_cat - action_cat
	diff_norm = diff**2
	diff_norm = torch.sum(diff_norm, dim=2)
	diff_norm = diff_norm + norm_smoothing
	diff_norm = torch.sqrt(diff_norm)
	diff_norm = diff_norm * beta * -1
	output    = F.softmax(diff_norm, dim=1)

	_print(2, "RBF_FUNCTION output shape: {}".format(output.shape))

	return output 

class Net(nn.Module):
	def __init__(self, params, env, state_size, action_size):
		super(Net, self).__init__()
		
		self.env = env
		self.params = params
		self.N = self.params['num_points']
		self.max_a = self.env.action_space.high[0]
		self.beta = self.params['temperature']

		self.buffer_object = buffer_class.buffer_class(max_length = self.params['max_buffer_size'],
													   seed_number = self.params['seed_number'])

		self.state_size, self.action_size = state_size, action_size

		self.value_side1 = nn.Linear(self.state_size, self.params['layer_size'])
		self.value_side1_parameters = self.value_side1.parameters()

		self.value_side2 = nn.Linear(self.params['layer_size'], self.params['layer_size'])
		self.value_side2_parameters = self.value_side2.parameters()

		self.value_side3 = nn.Linear(self.params['layer_size'], self.params['layer_size'])
		self.value_side3_parameters = self.value_side3.parameters()

		self.value_side4 = nn.Linear(self.params['layer_size'], self.N)
		self.value_side4_parameters = self.value_side4.parameters()

		self.drop = nn.Dropout(p=self.params['dropout_rate'])

		self.location_side1 = nn.Linear(self.state_size, self.params['layer_size'])
		torch.nn.init.xavier_uniform_(self.location_side1.weight)
		torch.nn.init.zeros_(self.location_side1.bias)

		self.location_side2 = []
		for _ in range(self.N):
			temp = nn.Linear(self.params['layer_size'], self.action_size)
			temp.weight.data.uniform_(-.1, .1)
			temp.bias.data.uniform_(-1, +1)
			#nn.init.uniform_(temp.bias,a = -2.0, b = +2.0)
			self.location_side2.append(temp)
		self.location_side2 = torch.nn.ModuleList(self.location_side2)
		self.criterion = nn.MSELoss()


		self.params_dic=[]
		self.params_dic.append({'params': self.value_side1_parameters, 'lr': self.params['learning_rate']})
		self.params_dic.append({'params': self.value_side2_parameters, 'lr': self.params['learning_rate']})
		
		self.params_dic.append({'params': self.value_side3_parameters, 'lr': self.params['learning_rate']})
		self.params_dic.append({'params': self.value_side4_parameters, 'lr': self.params['learning_rate']})
		self.params_dic.append({'params': self.location_side1.parameters(), 'lr': self.params['learning_rate_location_side']})

		for i in range(self.N):
		    self.params_dic.append({'params': self.location_side2[i].parameters(), 'lr': self.params['learning_rate_location_side']}) 
		self.optimizer = optim.RMSprop(self.params_dic)

	def forward(self, s, a):
		'''
			given a batch of s,a compute Q(s,a)
		'''
		centroid_values = self.get_centroid_values(s) # Want: [batch_dim x 1]
		centroid_locations = self.get_all_centroids_batch_mode(s)
		centroid_weights = rbf_function(centroid_locations, 
										a, 
										self.beta, 
										self.N, 
										self.params['norm_smoothing'])
		output = torch.mul(centroid_weights,centroid_values)
		output = output.sum(1,keepdim=True)
		_print(2, "Forward output shape: {}".format(output.shape))
		return output

	def get_centroid_values(self, s):
		'''
			given a batch of s, get V(s)_i for i in 1 through N
		'''
		temp = F.relu(self.value_side1(s))
		temp = F.relu(self.value_side2(temp))
		temp = F.relu(self.value_side3(temp))
		centroid_values = self.value_side4(temp)

		_print(2, "centroid values shape: {}".format(centroid_values.shape))

		return centroid_values

	def get_all_centroids_batch_mode(self, s):
		temp = F.relu(self.location_side1(s))
		temp = self.drop(temp)
		temp = [self.location_side2[i](temp).unsqueeze(0) for i in range(self.N)]
		temp = torch.cat(temp,dim=0)
		temp = self.max_a*torch.tanh(temp)
		centroid_locations = list(torch.split(temp, split_size_or_sections=1, dim=0))
		centroid_locations = [c.squeeze(0) for c in centroid_locations]

		_print(2, "Length of centroid_locations: {} and shape of each element: {}".format(len(centroid_locations), centroid_locations[0].shape))
		return centroid_locations

	def new_get_all_centroids_batch_mode(self, s):
		temp = F.relu(self.location_side1(s))
		temp = self.drop(temp)
		temp = [self.location_side2[i](temp).unsqueeze(0) for i in range(self.N)]
		temp = torch.cat(temp,dim=0)
		temp = self.max_a*torch.tanh(temp)

		centroid_locations = list(torch.split(temp, split_size_or_sections=1, dim=0))
		centroid_locations = [c.squeeze(0) for c in centroid_locations]
		return centroid_locations


	def get_best_centroid_batch(self, s):
		'''
			given a batch of states s
			determine max_{a} Q(s,a)
		'''
		all_centroids = self.get_all_centroids_batch_mode(s)
		values = self.get_centroid_values(s).unsqueeze(2)
		weights = rbf_function_single_batch_mode(all_centroids, 
												 self.beta, 
												 self.N, 
												 self.params['norm_smoothing'])
		allq = torch.bmm(weights, values).squeeze(2)
		best,indices = allq.max(1)
		if s.shape[0] == 1: #the function is called for a single state s
			index_star = indices.cpu().data.numpy()[0]
			a = list(all_centroids[index_star].cpu().data.numpy()[0])
			return best.cpu().data.numpy(), a
		else: #batch mode, for update
			return best.cpu().data.numpy()

	def new_get_best_centroid_batch(self, s):
		"""Doing a new one because I want to be able to directly compare the results."""
		'''
			given a batch of states s
			determine max_{a} Q(s,a)
		'''
		all_centroids = self.new_get_all_centroids_batch_mode(s)
		values = self.get_centroid_values(s).unsqueeze(2)
		weights = rbf_function_single_batch_mode(all_centroids, 
												 self.beta, 
												 self.N, 
												 self.params['norm_smoothing'])
		allq = torch.bmm(weights, values).squeeze(2)
		best,indices = allq.max(1)
		if s.shape[0] == 1: #the function is called for a single state s
			index_star = indices.cpu().data.numpy()[0]
			a = list(all_centroids[index_star].cpu().data.numpy()[0])
			return best.cpu().data.numpy(), a
		else: #batch mode, for update
			return best.cpu().data.numpy()


	def e_greedy_policy(self,s,episode,train_or_test):
		epsilon=1./numpy.power(episode,1./self.params['policy_parameter'])

		if train_or_test=='train' and random.random() < epsilon:
			a = self.env.action_space.sample()
			return a.tolist()
		else:
			self.eval()
			s_matrix = numpy.array(s).reshape(1,self.state_size)
			# q,a = self.new_get_best_centroid_batch( torch.FloatTensor(s_matrix).to(device))
			q,a = self.get_best_centroid_batch( torch.FloatTensor(s_matrix).to(device))
			self.train()
			return a

	def update(self, target_Q, count):

		if len(self.buffer_object.storage)<self.params['batch_size']:
			return 0
		else:
			pass
		s_matrix, a_matrix, r_matrix, done_matrix, sp_matrix = self.buffer_object.sample(self.params['batch_size'])
		r_matrix=numpy.clip(r_matrix,a_min=-self.params['reward_clip'],a_max=self.params['reward_clip'])

		s_matrix, a_matrix, r_matrix = torch.FloatTensor(s_matrix).to(device), torch.FloatTensor(a_matrix).to(device), torch.FloatTensor(r_matrix).to(device)
		done_matrix, sp_matrix = torch.FloatTensor(done_matrix).to(device), torch.FloatTensor(sp_matrix).to(device)

		# Q_star = target_Q.new_get_best_centroid_batch(sp_matrix)
		Q_star = target_Q.get_best_centroid_batch(sp_matrix)
		Q_star = Q_star.reshape((self.params['batch_size'],-1))
		Q_star = torch.FloatTensor(Q_star).to(device)
		y=r_matrix+self.params['gamma']*(1-done_matrix)*Q_star
		y_hat = self.forward(s_matrix,a_matrix)
		loss = self.criterion(y_hat,y.detach())
		self.zero_grad()
		loss.backward()
		self.optimizer.step()
		self.zero_grad()
		utils_for_q_learning.sync_networks(target = target_Q,
										   online = self, 
										   alpha = self.params['target_network_learning_rate'], 
										   copy = False)
		return loss.cpu().data.numpy()



if __name__=='__main__':
	print(torch.cuda.is_available())
	hyper_parameter_name=sys.argv[1]
	alg='rbf'
	params=utils_for_q_learning.get_hyper_parameters(hyper_parameter_name,alg)
	params['hyper_parameters_name']=hyper_parameter_name
	env=gym.make(params['env_name'])
	#env = gym.wrappers.Monitor(env, 'videos/'+params['env_name']+"/", video_callable=lambda episode_id: episode_id%10==0,force = True)
	params['env']=env
	params['seed_number']=int(sys.argv[2])
	testing = len(sys.argv) > 3 and sys.argv[3] == "--test"
	utils_for_q_learning.set_random_seed(params)
	s0=env.reset()
	utils_for_q_learning.action_checker(env)
	Q_object = Net(params,env,state_size=len(s0),action_size=len(env.action_space.low)).to(device)
	Q_object_target = Net(params,env,state_size=len(s0),action_size=len(env.action_space.low)).to(device)
	Q_object_target.eval()

	utils_for_q_learning.sync_networks(target = Q_object_target, online = Q_object, alpha = params['target_network_learning_rate'], copy = True)


	if testing:
		"""
		Comparing the new versions with the old
		1. new_get_all_centroids_batch_mode (one state input and multiple)
		2. new_get_best_centroid_batch (one state input and multiple)
		3. Get rid of the "single" version of rbf_function, but assert that the batch way is the same plus a state dim.
		"""

		Q_object.eval()

		s = env.reset()

		one_state_batch_np = numpy.array([s])
		many_state_batch_np = numpy.array([s,s,s,s])

		one_state_batch_torch = torch.as_tensor(one_state_batch_np, dtype=torch.float32)
		many_state_batch_torch = torch.as_tensor(many_state_batch_np, dtype=torch.float32)

		one_centroid_old = Q_object.get_all_centroids_batch_mode(one_state_batch_torch)
		one_centroid_new = Q_object.new_get_all_centroids_batch_mode(one_state_batch_torch)

		assert len(one_centroid_old) == len(one_centroid_new)
		for i in range(len(one_centroid_old)):
			assert torch.equal(one_centroid_old[i], one_centroid_new[i]), "{}  {}".format(one_centroid_old[i], one_centroid_new[i])


		many_centroid_old = Q_object.get_all_centroids_batch_mode(many_state_batch_torch)
		many_centroid_new = Q_object.new_get_all_centroids_batch_mode(many_state_batch_torch)

		assert len(many_centroid_old) == len(many_centroid_new)
		for i in range(len(many_centroid_old)):
			assert torch.equal(many_centroid_old[i], many_centroid_new[i])

		# return of old is value, action. value is numpy array (  dim (1, )  ), action is a list of one numpy array.
		one_best_value_old, one_best_action_old = Q_object.get_best_centroid_batch(one_state_batch_torch) # return value, action.
		one_best_value_new, one_best_action_new = Q_object.new_get_best_centroid_batch(one_state_batch_torch)

		# assert numpy.testing.assert_almost_equal(one_best_value_old, one_best_value_new)
		assert numpy.array_equal(one_best_value_old, one_best_value_new)
		assert one_best_value_old.shape == (1,)

		# assert len(one_best_value_old) == len(one_best_value_new) == 1, "{} {} ".format(len(one_best_value_old), len(one_best_value_new))
		assert one_best_action_old == one_best_action_new
		# assert numpy.array_equal(one_best_action_old[0], one_best_action_new[0])

		many_best_value_old = Q_object.get_best_centroid_batch(many_state_batch_torch) # return value, action.
		many_best_value_new = Q_object.new_get_best_centroid_batch(many_state_batch_torch)

		assert numpy.array_equal(many_best_value_old, many_best_value_new)


		print("Unit Tests Passed!")
		exit()

	import time

	G_li=[]
	loss_li = []
	for episode in range(params['max_episode']):

		Q_this_episode = Net(params,env,state_size=len(s0),action_size=len(env.action_space.low))
		utils_for_q_learning.sync_networks(target = Q_this_episode, online = Q_object, alpha = params['target_network_learning_rate'], copy = True)
		Q_this_episode.eval()

		s,done,t=env.reset(),False,0
		start = time.time()
		num_steps = 0
		while done==False:
			num_steps += 1
			a=Q_object.e_greedy_policy(s,episode+1,'train')
			sp,r,done,_=env.step(numpy.array(a))
			t=t+1
			done_p = False if t == env._max_episode_steps else done
			Q_object.buffer_object.append(s,a,r,done_p,sp)
			s=sp
		end = time.time()
		if num_steps != 0:
			_print(1, "e-greedy: {} per step".format((end - start) / num_steps))
		else:
			_print(1, 'no steps...')
		#now update the Q network
		start = time.time()
		loss = []
		for count in range(params['updates_per_episode']):
			temp = Q_object.update(Q_object_target, count)
			loss.append(temp)
		end = time.time()
		_print(1, "per update: {}".format((end - start) / params['updates_per_episode']))
		loss_li.append(numpy.mean(loss))


		if (episode % 10 == 0) or (episode == params['max_episode'] - 1):
			temp = []
			for _ in range(10):
				s,G,done,t=env.reset(),0,False,0
				while done==False:
					a=Q_object.e_greedy_policy(s,episode+1,'test')
					sp,r,done,_=env.step(numpy.array(a))
					s,G,t=sp,G+r,t+1
				temp.append(G)
			print("after {} episodes, learned policy collects {} average returns".format(episode,numpy.mean(temp)))
			G_li.append(numpy.mean(temp))	
			utils_for_q_learning.save(G_li,loss_li,params,alg)
