import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import gym



EP_MAX = 20000
EP_LEN = 2000
GAMMA = 0.9
A_LR = 0.01
C_LR = 0.0002
BATCH = 500
A_UPDATE_STEPS = 20
C_UPDATE_STEPS = 10
S_DIM, A_DIM = 4, 2  #状态长度   action长度

#采用PPO2这种方法
METHOD = [
    dict(name='kl_pen', kl_target=0.01, lam=0.5),   # KL penalty
    dict(name='clip', epsilon=0.2),                 # Clipped surrogate objective
][1]



class PPO(object):
    def __init__(self):
        self.sess = tf.Session()
        self.tfs = tf.placeholder(tf.float32,[None,S_DIM],'state')

        #critic
        with tf.variable_scope('critic'):
            l1 = tf.layers.dense(self.tfs,100,tf.nn.relu)
            l1 = tf.layers.dense(l1, 100, tf.nn.relu)
            self.v = tf.layers.dense(l1,1) # state-value
            self.tfdc_r = tf.placeholder(tf.float32,[None,1],'discounted_r')
            self.advantage = self.tfdc_r - self.v #???
            self.closs = tf.reduce_mean(tf.square(self.advantage))
            self.ctrain_op = tf.train.AdamOptimizer(C_LR).minimize(self.closs)


        #actor  pi是一个正态分布器
        pi,pi_params = self._build_anet('pi',trainable=True)
        oldpi,oldpi_params = self._build_anet('oldpi',trainable=False)
        with tf.variable_scope('sample_action'):
            self.sample_op = tf.expand_dims(tf.argmax(oldpi,axis=1),axis=1)  #去掉维度，输出数组
            # print(type(self.sample_op))
            # print(self.sample_op.shape)  #[n,1]
            # exit()
        with tf.variable_scope('update_oldpi'):
            self.update_oldpi_op = [oldp.assign(p) for p,oldp in zip(pi_params,oldpi_params)]

        self.tfa = tf.placeholder(tf.int32,[None,1],'action')
        self.tfadv = tf.placeholder(tf.float32,[None,1],'advantage')
        with tf.variable_scope('loss'):
            with tf.variable_scope('surrogate'):
                onehot_a=tf.one_hot(tf.squeeze(self.tfa,axis=1),2)
                ratio = tf.reduce_sum(pi*onehot_a,axis=1,keep_dims=True)/tf.reduce_sum(oldpi*onehot_a,axis=1,keep_dims=True)
                surr = ratio * self.tfadv  #(?, 1)

            if METHOD['name'] == 'kl_pen':
                self.tflam = tf.placeholder(tf.float32,None,'lambda')
                kl = tf.distributions.kl_divergence(oldpi,pi)
                self.kl_mean = tf.reduce_mean(kl)
                self.aloss = -tf.reduce_mean(surr-self.tflam * kl)

            else:
                self.aloss = -tf.reduce_mean(tf.minimum(surr,
                                                        tf.clip_by_value(ratio, 1. - METHOD['epsilon'],
                                                                         1. + METHOD['epsilon']) * self.tfadv)
                                             )


            with tf.variable_scope('atrain'):
                self.atrain_op = tf.train.RMSPropOptimizer(A_LR).minimize(self.aloss)

            tf.summary.FileWriter("log/", self.sess.graph)

            self.sess.run(tf.global_variables_initializer())

    def update(self,s,a,r):

        #adv = self.sess.run(self.advantage,{self.tfs:s,self.tfdc_r:r}) # 得到advantage value
        adv=r
        # update actor
        if METHOD['name'] == 'kl_pen':
            for _ in range(A_UPDATE_STEPS):
                _,kl = self.sess.run([self.atrain_op,self.kl_mean],
                                     {self.tfs:s,self.tfa:a,self.tfadv:adv,self.tflam:METHOD['lam']})
                if kl > 4 * METHOD['kl_target']:
                    break
                elif kl < METHOD['kl_target'] / 1.5:  # adaptive lambda, this is in OpenAI's paper
                    METHOD['lam'] /= 2
                elif kl > METHOD['kl_target'] * 1.5:
                    METHOD['lam'] *= 2
                METHOD['lam'] = np.clip(METHOD['lam'], 1e-4, 10)  # sometimes explode, this clipping is my solution

        else:   # clipping method, find this is better (OpenAI's paper)
            [self.sess.run(self.atrain_op, {self.tfs: s, self.tfa: a, self.tfadv: adv}) for _ in range(A_UPDATE_STEPS)]

        # update critic
        #[self.sess.run(self.ctrain_op, {self.tfs: s, self.tfdc_r: r}) for _ in range(C_UPDATE_STEPS)]
        self.sess.run(self.update_oldpi_op)

    def _build_anet(self,name,trainable):
        with tf.variable_scope(name):
            l1 = tf.layers.dense(self.tfs,100,tf.nn.relu,trainable=trainable)
            l2 = tf.layers.dense(l1, 100, tf.nn.relu, trainable=trainable)
            #输出行动的概率
            l3 = tf.layers.dense(l2, A_DIM, tf.nn.softmax, trainable=trainable)
            # mu = 2 * tf.layers.dense(l1,A_DIM,tf.nn.tanh,trainable=trainable)
            # #>0
            # sigma = tf.layers.dense(l1,A_DIM,tf.nn.softplus,trainable=trainable)
            # norm_dist = tf.distributions.Normal(loc=mu,scale=sigma) # 一个正态分布,loc为均值，scale为标准差
        params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES,scope=name)
        return l3,params

    def choose_action(self,s):
        s = s[np.newaxis,:]  #增加一个维度
        a = self.sess.run(self.sample_op,{self.tfs:s})[0]
        # print("**********",type(a))
        # print(a.shape)
        # exit()
        return a

    def get_v(self,s):
        if s.ndim < 2:s = s[np.newaxis,:]
        return self.sess.run(self.v,{self.tfs:s})[0,0]

env = gym.make('CartPole-v0').unwrapped
print(env.action_space) #Box(1,)

print(env.observation_space) #Box(3,)
print(env.observation_space.high)  #[1. 1. 8.]
print(env.observation_space.low)#[-1. -1. -8.]
print("**************************************")

ppo = PPO()
all_ep_r = []

for ep in range(EP_MAX):  #200
    s = env.reset()
    buffer_s, buffer_a, buffer_r = [], [], []
    ep_r = 0
    while True:#for t in range(EP_LEN):    # in one episode  200
        env.render()
        #输入state，输出action
        a = ppo.choose_action(s) # 根据一个正态分布，选择一个action,shape=(1,)
        # print(a.shape)
        # exit()
        s_, r, done, _ = env.step(a[0])
        buffer_s.append(s)
        buffer_a.append(a)
        if done:
            r=-1.0
        buffer_r.append(r)    # normalize reward, find to be useful
        s = s_
        ep_r += r  #单场游戏累积奖励

        # update ppo
        if done:#(t+1) % BATCH == 0 or t == EP_LEN-1:
            # v_s_ = ppo.get_v(s_) #s_为本步走后的状态，根据状态网络计算出一个值
            v_s_=0
            discounted_r = []
            for r in buffer_r[::-1]:#本步产生的奖励只与本步以后有关，与本步以前无关
                v_s_ = r + GAMMA * v_s_
                discounted_r.append(v_s_) # v(s) = r + gamma * v(s+1)
            discounted_r.reverse() #反转
            #求平均值
            dis_mean=np.mean(discounted_r)
            discounted_r=discounted_r-dis_mean
            # print((np.array(discounted_r)[:, np.newaxis]).shape)#(32, 1)
            # exit()

            bs, ba, br = np.vstack(buffer_s), np.vstack(buffer_a), np.array(discounted_r)[:, np.newaxis]
            # print(bs.shape)  #(32, 3)
            # print(ba.shape)  #(32, 1)
            # print(br.shape)  #(32, 1)
            # exit()
            buffer_s, buffer_a, buffer_r = [], [], []  #经验池清空
            ppo.update(bs, ba, br)
            break
    if ep == 0:
        all_ep_r.append(ep_r)
    else:
        all_ep_r.append(all_ep_r[-1]*0.9 + ep_r*0.1)
    print(
        'Ep: %i' % ep,
        "|Ep_r: %i" % ep_r,
        ("|Lam: %.4f" % METHOD['lam']) if METHOD['name'] == 'kl_pen' else '',
    )

plt.plot(np.arange(len(all_ep_r)), all_ep_r)
plt.xlabel('Episode')
plt.ylabel('Moving averaged episode reward')
plt.show()
