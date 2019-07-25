#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 29 14:38:26 2019
@author: mzaiss 
"""

experiment_id = 't04_tgtBSSFP_tsk_BSSFP_32_alpha_2_prep'
sequence_class = "BSSFP"
experiment_description = """
bSSFP with alpha/2 prep
"""

import os, sys
import numpy as np
import scipy
import scipy.io
from  scipy import ndimage
import torch
import cv2
import matplotlib.pyplot as plt
from torch import optim
import core.spins
import core.scanner
import core.opt_helper
import core.target_seq_holder

use_gpu = 1
gpu_dev = 2
do_scanner_query = True

# NRMSE error function
def e(gt,x):
    return 100*np.linalg.norm((gt-x).ravel())/np.linalg.norm(gt.ravel())
    
# torch to numpy
def tonumpy(x):
    return x.detach().cpu().numpy()

# get magnitude image
def magimg(x):
  return np.sqrt(np.sum(np.abs(x)**2,2))

def magimg_torch(x):
  return torch.sqrt(torch.sum(torch.abs(x)**2,1))

def phaseimg(x):
    return np.angle(1j*x[:,:,1]+x[:,:,0])


# device setter
def setdevice(x):
    if use_gpu:
        x = x.cuda(gpu_dev)    
    return x
    
def stop():
    sys.tracebacklimit = 0
    class ExecutionControl(Exception): pass
    raise ExecutionControl('stopped by user')
    sys.tracebacklimit = 1000

# define setup
sz = np.array([42,42])                                           # image size
NRep = sz[1]                                          # number of repetitions
T = sz[0] + 4                                        # number of events F/R/P
NSpins = 8**2                                # number of spin sims in each voxel
NCoils = 1                                  # number of receive coil elements
import time; today_datestr = time.strftime('%y%m%d')
noise_std = 0*1e0                               # additive Gaussian noise std

NVox = sz[0]*sz[1]

#############################################################################
## Init spin system ::: #####################################

# initialize scanned object
spins = core.spins.SpinSystem(sz,NVox,NSpins,use_gpu+gpu_dev)

cutoff = 1e-12

real_phantom = scipy.io.loadmat('../../data/phantom2D.mat')['phantom_2D']
real_phantom_resized = np.zeros((sz[0],sz[1],5), dtype=np.float32)
for i in range(5):
    t = cv2.resize(real_phantom[:,:,i], dsize=(sz[0],sz[1]), interpolation=cv2.INTER_CUBIC)
    if i == 0:
        t[t < 0] = 0
    elif i == 1 or i == 2:
        t[t < cutoff] = cutoff
        
    real_phantom_resized[:,:,i] = t

real_phantom_resized[:,:,1] *= 1 # Tweak T1
real_phantom_resized[:,:,2] *= 1 # Tweak T2
real_phantom_resized[:,:,3] *= 1  # Tweak dB0

current_b0map = np.load("../../data/current_b0map.npy")
real_phantom_resized[:,:,3] = current_b0map

b0mask = np.abs(real_phantom_resized[:,:,3])  < 10

#real_phantom_resized[2*sz[0]//3:,:,3] *= 0.5 # Tweak dB0
 
spins.set_system(real_phantom_resized)
# end initialize scanned object

plt.subplot(141)
plt.imshow(real_phantom_resized[:,:,0], interpolation='none')
plt.title("PD")
plt.subplot(142)
plt.imshow(real_phantom_resized[:,:,1], interpolation='none')
plt.title("T1")
plt.subplot(143)
plt.imshow(real_phantom_resized[:,:,2], interpolation='none')
plt.title("T2")
plt.subplot(144)
plt.imshow(real_phantom_resized[:,:,3], interpolation='none')
plt.title("inhom")
plt.show()
print('use_gpu = ' +str(use_gpu)) 

#begin nspins with R*
R2 = 30.0
omega = np.linspace(0+1e-5,1-1e-5,NSpins) - 0.5    # cutoff might bee needed for opt.
#omega = np.random.rand(NSpins,NVox) - 0.5
omega = np.expand_dims(omega[:],1).repeat(NVox, axis=1)
omega*=0.9  # cutoff large freqs
omega = R2 * np.tan ( np.pi  * omega)

if NSpins==1:
    omega[:,:]=0
    
spins.omega = torch.from_numpy(omega.reshape([NSpins,NVox])).float()
spins.omega = setdevice(spins.omega)
#end nspins with R*


#############################################################################
## Init scanner system ::: #####################################
scanner = core.scanner.Scanner_fast(sz,NVox,NSpins,NRep,T,NCoils,noise_std,use_gpu+gpu_dev)
adc_mask = torch.from_numpy(np.ones((T,1))).float()
adc_mask[:2]  = 0
adc_mask[-2:] = 0
scanner.set_adc_mask(adc_mask=setdevice(adc_mask))

# RF events: flips and phases
flips = torch.zeros((T,NRep,2), dtype=torch.float32)
flips[0,:,0] = 45*np.pi/180  # GRE/FID specific, GRE preparation part 1 : 90 degree excitation 
#flips[1,0,0] = -2.5*np.pi/180  # GRE/FID specific, GRE preparation part 1 : 90 degree excitation 
#flips[0,:,1] = torch.rand(flips.shape[1])*90*np.pi/180

# randomize RF phases
#flips[0,:,1] = torch.tensor(scanner.phase_cycler[:NRep]).float()*np.pi/180
#flips[0,:,1] = torch.tensor(np.mod(np.arange(0,int(sz[0])*180),180)*np.pi/180)
flips[0,:,1] = torch.tensor(np.mod(np.arange(0,int(sz[0])*20,20),360)*np.pi/180)  # 180 phace cycling for bSSFP
flips[0,0,0] = flips[0,0,0]/2  # bssfp specific, alpha/2 prep, to avoid many dummies


flips = setdevice(flips)

scanner.init_flip_tensor_holder()
B1plus = torch.zeros((scanner.NCoils,1,scanner.NVox,1,1), dtype=torch.float32)
B1plus[:,0,:,0,0] = torch.from_numpy(real_phantom_resized[:,:,4].reshape([scanner.NCoils, scanner.NVox]))
B1plus[B1plus == 0] = 1    # set b1+ to one, where we dont have phantom measurements
#B1plus[:] = 1
scanner.B1plus = setdevice(B1plus)    
scanner.set_flip_tensor_withB1plus(flips)

# rotate ADC according to excitation phase
rfsign = ((flips[0,:,0]) < 0).float()
scanner.set_ADC_rot_tensor(-flips[0,:,1] + np.pi/2 + np.pi*rfsign) #GRE/FID specific

# event timing vector 
event_time = torch.from_numpy(0.08*1e-3*np.ones((scanner.T,scanner.NRep))).float()
event_time[0,:] =  2e-3     + 0.5*1e-3*0
event_time[1,:] = 0.3*1e-3
event_time[-2,:] = 0.3*1e-3
event_time[-1,:] = 2*1e-3 + 0.3 - 0.5*1e-3*0  #+0.4*1e-3
#event_time[-1,:] = 1.2           # GRE/FID specific, GRE relaxation time: choose large for fully relaxed  >=1, choose small for FLASH e.g 10ms
event_time = setdevice(event_time)

TR=torch.sum(event_time[:,1])*1000
TE=torch.sum(event_time[:int(sz[0]/2+2),1])*1000

TE_180  = torch.sum(event_time[:int(sz[0]/2+2),1]) # time after 180 til center k-space
TE_180_2= torch.sum(event_time[int(sz[0]/2+2):,1]) # time after center k-space til next 180

TE_180_centerpulse   = torch.sum(event_time[:int(sz[0]/2+2),1]) - event_time[0,0] /2 # time center 180 till center k-space
TE_180_2_centerpulse = torch.sum(event_time[int(sz[0]/2+2):,1]) + event_time[0,0] /2 # time after center k-space till next 180 center pulse


# gradient-driver precession
# Cartesian encoding
grad_moms = torch.zeros((T,NRep,2), dtype=torch.float32) 

grad_moms[1,:,0] = -sz[0]/2         # GRE/FID specific, rewinder in second event block
grad_moms[1,:,1] = torch.linspace(-int(sz[1]/2),int(sz[1]/2-1),int(NRep))  # phase encoding in second event block
grad_moms[2:-2,:,0] = torch.ones(int(sz[0])).view(int(sz[0]),1).repeat([1,NRep]) # ADC open, readout, freq encoding
grad_moms[-2,:,0] = grad_moms[1,:,0]     # bssfp specific, xrewinder
grad_moms[-2,:,1] = -grad_moms[1,:,1]      # bssfp specific, yblip rewinder

grad_moms*=1
#     centric ordering
#grad_moms[1,:,1] = 0
#for i in range(1,int(sz[1]/2)+1):
#    grad_moms[1,i*2-1,1] = (-i)
#    if i < sz[1]/2:
#        grad_moms[1,i*2,1] = i
#grad_moms[-2,:,1] = -grad_moms[1,:,1]     # backblip

grad_moms = setdevice(grad_moms)

# end sequence 
scanner.init_gradient_tensor_holder()
scanner.set_gradient_precession_tensor(grad_moms,sequence_class)  # refocusing=False for GRE/FID, adjust for higher echoes

#############################################################################
## Forward process ::: ######################################################
    
#scanner.do_dummy_scans(spins,event_time,nrep=0)   # do dummies
# forward/adjoint pass
scanner.forward_fast(spins, event_time,do_dummy_scans=False)
#scanner.forward_mem(spins, event_time,do_dummy_scans=False)
scanner.adjoint()

# try to fit this
target = scanner.reco.clone()

#hfghfgh
   
# save sequence parameters and target image to holder object
targetSeq = core.target_seq_holder.TargetSequenceHolder(flips,event_time,grad_moms,scanner,spins,target)

if True: # check sanity: is target what you expect and is sequence what you expect
    targetSeq.print_status(True, reco=None)
    
    #plt.plot(np.cumsum(tonumpy(scanner.ROI_signal[:,0,0])),tonumpy(scanner.ROI_signal[:,0,1:3]), label='x')
#    for i in range(3):
#        plt.subplot(1, 3, i+1)
#        plt.plot(tonumpy(scanner.ROI_signal[:,:,1+i]).transpose([1,0]).reshape([(scanner.T)*scanner.NRep]) )
#        plt.title("ROI_def %d" % scanner.ROI_def)
#        fig = plt.gcf()
#        fig.set_size_inches(16, 3)
    plt.show()
    
    #targetSeq.export_to_matlab(experiment_id)
    
    if do_scanner_query:
        targetSeq.export_to_pulseq(experiment_id,today_datestr,sequence_class, plot_seq=False)
        scanner.send_job_to_real_system(experiment_id,today_datestr)
        
        scanner.get_signal_from_real_system(experiment_id,today_datestr)
        
        plt.subplot(131)
        scanner.adjoint()
        plt.imshow(magimg(tonumpy(scanner.reco.detach()).reshape([sz[0],sz[1],2])), interpolation='none')
        plt.title("real ADJOINT")
        plt.subplot(132)
        scanner.do_ifft_reco()
        plt.imshow(magimg(tonumpy(scanner.reco.detach()).reshape([sz[0],sz[1],2])), interpolation='none')
        plt.title("real IFFT")    
        plt.subplot(133)
        plt.imshow(magimg(tonumpy(target).reshape([sz[0],sz[1],2])), interpolation='none')
        plt.title("simulation ADJOINT")    
        plt.show()
        
        plt.subplot(131)
        scanner.adjoint()
        measreco = tonumpy(scanner.reco.detach())
        plt.imshow(phaseimg(measreco.reshape([sz[0],sz[1],2]))*180/np.pi, interpolation='none')
        plt.title("real ADJOINT")
        plt.clim(-180,180)
        plt.subplot(132)
        scanner.do_ifft_reco()
        plt.imshow(phaseimg(tonumpy(scanner.reco.detach()).reshape([sz[0],sz[1],2]))*180/np.pi, interpolation='none')
        plt.title("real IFFT")  
        plt.clim(-180,180)
        plt.subplot(133)
        plt.imshow(phaseimg(tonumpy(target).reshape([sz[0],sz[1],2]))*180/np.pi, interpolation='none')

        plt.title("simulation ADJOINT")   
        plt.clim(-180,180)
        plt.show()
               
    simphase=phaseimg(tonumpy(target).reshape([sz[0],sz[1],2]))/np.pi
    plt.hist(simphase.ravel(),bins=100)
    plt.title("sim phase hist")
    plt.show()
    
    measphase=phaseimg(measreco.reshape([sz[0],sz[1],2]))/np.pi
    plt.hist(measphase.ravel(),bins=100)
    plt.title("meas phase hist")
    plt.show()    
                    
    stop()
    
for i in range(3):
    cline=scanner.signal[0,2:-2,1+i,:2,0]
    #plt.plot(tonumpy(cline[:,0]))
    plt.plot(tonumpy(cline[:,1]))
    #plt.plot(np.sqrt(tonumpy(cline[:,0])**2+tonumpy(cline[:,1])**2))
    plt.ion()
    plt.show()
#plt.plot(tonumpy(cline[:,0]))

#plt.plot(np.angle(tonumpy(cline[:,0])+1j*tonumpy(cline[:,1])))
        
    # %% ###     OPTIMIZATION functions phi and init ######################################################
#############################################################################    
        
def init_variables():
    adc_mask = targetSeq.adc_mask.clone()
    
    flips = targetSeq.flips.clone()
    #flips[0,:,:]=flips[0,:,:]*0
#    flips[0,:,1] = torch.tensor(np.mod(np.arange(0,int(sz[0])*180,180),360)*np.pi/180)  # 180 phace cycling for bSSFP
    flips = setdevice(flips)
    
    flip_mask = torch.ones((scanner.T, scanner.NRep, 2)).float()     
    flip_mask[1:,:,:] = 0
    flip_mask = setdevice(flip_mask)
    flips.zero_grad_mask = flip_mask
      
    event_time = targetSeq.event_time.clone()
    #event_time = torch.from_numpy(1e-7*np.random.rand(scanner.T,scanner.NRep)).float()
    #event_time*=0.5
    #event_time[:,0] = 0.4*1e-3  
    #event_time[-1,:] = 0.012 # target is fully relaxed GRE (FA5), task is FLASH with TR>=12ms
    event_time = setdevice(event_time)
    
    event_time_mask = torch.ones((scanner.T, scanner.NRep)).float()        
    event_time_mask[2:-2,:] = 0
    event_time_mask = setdevice(event_time_mask)
    event_time.zero_grad_mask = event_time_mask
        
    grad_moms = targetSeq.grad_moms.clone()

    grad_moms_mask = torch.zeros((scanner.T, scanner.NRep, 2)).float()        
    #grad_moms_mask[1,:,:] = 1
    grad_moms_mask[-2,:,:] = 1
    grad_moms_mask = setdevice(grad_moms_mask)
    grad_moms.zero_grad_mask = grad_moms_mask
    
    #grad_moms[1,:,0] = grad_moms[1,:,0]*0    # remove rewinder gradients
    #grad_moms[1,:,1] = -grad_moms[1,:,1]*0      # GRE/FID specific, SPOILER
    
    grad_moms[-2,:,0] = grad_moms[1,:,0]*0.8      # remove spoiler gradients
    grad_moms[-2,:,1] = -grad_moms[1,:,1]*0.8      # GRE/FID specific, SPOILER
        
    return [adc_mask, flips, event_time, grad_moms]
    
def reparameterize(opt_params):
    return opt_params

def phi_FRP_model(opt_params,aux_params):
    
    adc_mask,flips,event_time,grad_moms = reparameterize(opt_params)

    scanner.init_flip_tensor_holder()
    scanner.set_flip_tensor_withB1plus(flips)    
    # rotate ADC according to excitation phase
    rfsign = ((flips[0,:,0]) < 0).float()
    scanner.set_ADC_rot_tensor(-flips[0,:,1] + np.pi/2 + np.pi*rfsign)  # GRE/FID specific, this must be the excitation pulse
          
    scanner.init_gradient_tensor_holder()          
    scanner.set_gradient_precession_tensor(grad_moms,sequence_class) # GRE/FID specific, maybe adjust for higher echoes
         
    # forward/adjoint pass
    #scanner.forward_mem(spins, event_time)
    scanner.forward_fast(spins, event_time)
    scanner.adjoint()

    lbd = 0*1e1         # switch on of SAR cost
    loss_image = (scanner.reco - targetSeq.target_image)
    #loss_image = (magimg_torch(scanner.reco) - magimg_torch(targetSeq.target_image))   # only magnitude optimization
    loss_image = torch.sum(loss_image.squeeze()**2/NVox)
    loss_sar = torch.sum(flips[:,:,0]**2)
    
    lbd_kspace = 1e1*0
    
    k = torch.cumsum(grad_moms, 0)
    k = k*torch.roll(scanner.adc_mask, -1).view([T,1,1])
    k = k.flatten()
    mask = (torch.abs(k) > sz[0]/2).float()
    k = k * mask
    loss_kspace = torch.sum(k**2) / (NRep*torch.sum(scanner.adc_mask))
    
    loss = loss_image + lbd*loss_sar + lbd_kspace*loss_kspace
    
    print("loss_image: {} loss_sar {} loss_kspace {}".format(loss_image, lbd*loss_sar, lbd_kspace*loss_kspace))
    
    phi = loss
  
    ereco = tonumpy(scanner.reco.detach()).reshape([sz[0],sz[1],2])
    error = e(tonumpy(targetSeq.target_image).ravel(),ereco.ravel())     
    
    return (phi,scanner.reco, error)
        
# %% # OPTIMIZATION land

opt = core.opt_helper.OPT_helper(scanner,spins,None,1)
opt.set_target(tonumpy(targetSeq.target_image).reshape([sz[0],sz[1],2]))
opt.target_seq_holder=targetSeq
opt.experiment_description = experiment_description

opt.optimzer_type = 'Adam'
opt.opti_mode = 'seq'
# 
opt.set_opt_param_idx([3]) # ADC, RF, time, grad
opt.custom_learning_rate = [0.01,0.1,0.1,0.1]

opt.set_handles(init_variables, phi_FRP_model,reparameterize)
opt.scanner_opt_params = opt.init_variables()

opt.train_model(training_iter=1000, do_vis_image=False, save_intermediary_results=True) # save_intermediary_results=1 if you want to plot them later
opt.train_model(training_iter=1000, do_vis_image=True, save_intermediary_results=True) # save_intermediary_results=1 if you want to plot them later

_,reco,error = phi_FRP_model(opt.scanner_opt_params, opt.aux_params)

# plot
targetSeq.print_status(True, reco=None)
opt.print_status(True, reco)

stop()

# %% # save optimized parameter history

new_exp_id=experiment_id+'_multiitertest';
targetSeq.export_to_matlab(new_exp_id)
targetSeq.export_to_pulseq(new_exp_id, sequence_class)
opt.save_param_reco_history(new_exp_id, sequence_class)
opt.save_param_reco_history_matlab(new_exp_id)
opt.export_to_matlab(new_exp_id)