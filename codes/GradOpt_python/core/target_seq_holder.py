import numpy as np
import torch
from termcolor import colored
import matplotlib.pyplot as plt
# target images / sequence parameters holder
# torch to numpy
def tonumpy(x):
    return x.detach().cpu().numpy()

def magimg(x):
    return np.sqrt(np.sum(np.abs(x)**2,2))

def phaseimg(x):
    return np.angle(1j*x[:,:,1]+x[:,:,0])

class TargetSequenceHolder():
    def __init__(self):
        
        self.target_image = None
        self.sz = None
        self.flips = None
        self.grad_moms = None
        self.event_time = None
        self.adc_mask = None
        
        self.ROI_signal = None                # measured signal (NCoils,T,NRep,4)
        self.ROI_def = 1
        
    def print_status(self, do_vis_image=False, reco=None):
        if do_vis_image:
            #sz=self.spins.sz
            #recoimg = tonumpy(reco).reshape([sz[0],sz[1],2])
            
            recoimg= (tonumpy(self.target_image).reshape([self.sz[0],self.sz[1],2]))
            
    
            # clear previous figure stack            
            plt.clf()            
            
            ax1=plt.subplot(151)
            ax=plt.imshow(magimg(recoimg), interpolation='none')
            #plt.clim(0,1)
            fig = plt.gcf()
            fig.colorbar(ax)
            plt.title('target reco')
            plt.ion()
            
            plt.subplot(152, sharex=ax1, sharey=ax1)
            ax=plt.imshow(phaseimg(recoimg), interpolation='none')
            plt.clim(-np.pi,np.pi)
            fig = plt.gcf()
            fig.colorbar(ax)
            plt.title('target reco phase')
            plt.ion()
               
            plt.subplot(153)
            try:
                FA=self.flips[:,:,0]
            except:
                FA=self.flips
                
            ax=plt.imshow(np.transpose(tonumpy(FA*180/np.pi),[1,0]),cmap=plt.get_cmap('nipy_spectral'))
            plt.ion()
            plt.title('FA [\N{DEGREE SIGN}]')
            plt.clim(-90,270)
            fig = plt.gcf()
            fig.colorbar(ax)
            fig.set_size_inches(18, 3)
            
            
            plt.subplot(154)
            ax=plt.imshow(tonumpy(torch.abs(self.event_time)[:,:,0].permute([1,0])),cmap=plt.get_cmap('nipy_spectral'))
            plt.ion()
            plt.title('TR [s]')
            fig = plt.gcf()
            fig.set_size_inches(18, 3)
            fig.colorbar(ax)
              
            
            ax1=plt.subplot(2, 5, 5)
            ax=plt.imshow(tonumpy(self.grad_moms[:,:,0].permute([1,0])),cmap=plt.get_cmap('nipy_spectral'))
            plt.ion()
            plt.title('gradx')
            fig = plt.gcf()
            fig.set_size_inches(18, 3)
            fig.colorbar(ax)
               
            
            ax1=plt.subplot(2, 5, 10)
            ax=plt.imshow(tonumpy(self.grad_moms[:,:,1].permute([1,0])),cmap=plt.get_cmap('nipy_spectral'))
            plt.ion()
            fig = plt.gcf()
            fig.set_size_inches(18, 3)
            fig.colorbar(ax)
            
            plt.show()
            plt.pause(0.02)
            
    
