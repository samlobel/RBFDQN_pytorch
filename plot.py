import matplotlib as mpl
mpl.use('TkAgg')
import matplotlib.pyplot as plt
import numpy


def truncate(li):
	#print([len(x) for x in li])
	N = numpy.min([len(x) for x in li])
	return [l[:N] for l in li]


def smooth(li):
	window = 2
	y = li
	y_smooth = [numpy.mean(y[max(x - window, 0):x + window]) for x in range(len(y))]
	return y_smooth


def compute_fina_mean_and_std(li):
	li_last = [l[-1] for l in li]
	print(numpy.mean(li_last))
	print(numpy.std(li_last) / 20)


#[20,31,40,45]
#for hyper_parameter_name in ['10','11','12','13','14','15','16','17','lunar_old']:
#for hyper_parameter_name in [0,1,2,3]:
#for hyper_parameter_name in [20,21,22,23]:
#for hyper_parameter_name in range(40,55):
#for hyper_parameter_name in range(70,82):
#for hyper_parameter_name in range(82,85):
#for hyper_parameter_name in range(85,100):
problems_name = [
    'Pendulum',
    'LunarLander',
    'Bipedal',
    'Hopper',
    'Cheetah',
    'Ant',
    'InvertedDoublePendulum',
    'InvertedPendulum',
    'Reacher'
]
ylim_down = [-1500, -350, -100, -500, -500, -500, 0, 0, -80]
ylim_up = [-100, 235, 300, 3000, 8000, 3000, 9350, 1000, -4]
#y_ticks = [[-1000,-150],[-200,220],[0,250],[0,2500],[0,7500],[0,3000],[0,9000],[0,1000],[-50,-4]]
#setting_li=[0]
#setting_li=[0]+list(range(900,910))
#setting_li=[0]
labels = [
    '100 updates',
    '200 updates',
    '200 updates slow target',
    '200 updates slowest target',
    '200 updates slowest! target',
    '200 updates less target updates',
    '200 updates less target updates'
]
colors = ['blue', 'orange', 'brown', 'black', 'green', 'blue', 'black', 'purple']
for problem in range(6 ):
	plt.subplot(3, 2, problem + 1)
	print(problems_name[problem])
	#for setting in range(9):
	
	
	for setting in [0]:
		hyper_parameter_name = str(problem) + str(setting)
		acceptable_len = 00
		li = []
		for seed_num in range(10):
			try:
				temp = numpy.loadtxt("rbf_results/" + str(hyper_parameter_name) +
				                     "/loss_" + str(seed_num) + ".txt")
				temp = numpy.loadtxt("rbf_results/" + str(hyper_parameter_name) +"/" + str(seed_num) + ".txt")
				plt.plot(smooth(temp),lw=1,color=colors[setting%len(colors)])
				if len(temp) > acceptable_len:
					li.append(temp)
					
					print(hyper_parameter_name,seed_num,numpy.mean(temp[-10:]),len(temp))	
			except:
				#print("problem")
				pass
		#print([len(x) for x in li])
		li = truncate(li)
		print(hyper_parameter_name,len(li[0]),
		      numpy.mean(numpy.mean(li, axis=0)[-3:]),numpy.mean(li),len(li))
		plt.plot(smooth(numpy.mean(li, axis=0)), label=setting, lw=4, color=colors[setting%len(colors)])
		#plt.ylim([ylim_down[problem],ylim_up[problem]])
		#plt.yticks([ylim_down[problem],ylim_up[problem]])
	#plt.title(problems_name[problem])
	#plt.legend()
plt.subplots_adjust(wspace=0.5, hspace=1)
plt.show()
