import tensorflow as tf
import math
import numpy as np
# a=tf.distributions.Normal(loc=0.0,scale=1.0)
# a=tf.Variable([[1,2],[3,4],[5,6]])
# init=tf.global_variables_initializer()
# with tf.Session() as sess:
#     sess.run(init)
#
#     print(sess.run(tf.reduce_sum(a,axis=1,keep_dims=True)))

a=[1,2,3,4,5]
print(a-np.mean(a))


# a=[1,2,3,4,5]
# for r in a[::-1]:
#     print(r)