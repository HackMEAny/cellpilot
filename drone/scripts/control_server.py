#!/usr/bin/python
# Copyright (c) 2015, Netforce Co., Ltd.
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys
import socket
import time
import picamera
import raspilot_usart

NUM_PWM=8
NO_SIGNAL_DELAY=15000
receive_mode="NO_SIGNAL"

target_ip=sys.argv[1]
target_port=int(sys.argv[2])

framerate=10
bitrate=32000
intra_period=5*framerate
vflip=False
hflip=False
max_pkt_size=1200
last_cmd_t=None

cam=None
pkt_no=0

sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.bind(("",5099))
sock.setblocking(0)

def send_video_pkt(pkt):
    global pkt_no
    if len(pkt)<=max_pkt_size:
        head=struct.pack(">I",pkt_no)
        pkt_no+=1
        data="v"+head+pkt
        print("send video packet %d (%d bytes)"%(pkt_no,len(data)))
        sock.sendto(data,(target_ip,target_port))
    else:
        offset=0
        while offset<len(pkt):
            chunk=pkt[offset:offset+max_pkt_size-5]
            head=struct.pack(">I",pkt_no)
            pkt_no+=1
            data="V"+head+chunk
            print("send jumbo video packet %d (%d bytes)"%(pkt_no,len(data)))
            sock.sendto(data,(target_ip,target_port))
            offset+=len(chunk)

class VideoOutput(object):
    def write(self,video_data):
        if not ins:
            print("don't send video because no instruments")
            return
        try:
            send_video_pkt(video_data)
        except Exception as e:
            print("error: %s"%e)
            import traceback
            traceback.print_exc()

def start_video():
    print("start_video")
    global cam
    if cam:
        cam.close()
    cam=picamera.PiCamera(resolution=(320,240),framerate=framerate)
    cam.vflip=vflip
    cam.hflip=hflip
    cam.start_recording(VideoOutput(),format="h264",bitrate=bitrate,intra_period=intra_period)

def signal_lost():
    receive_mode="NO_SIGNAL"
    for chan in range(0,NUM_PWM):
        raspilot_usart.set_pwm(chan,0)

start_video()

try:
    while True:
        t=int(time.time()*1000)
        try:
            while True:
                try:
                    pkt,(from_ip,from_port)=sock.recvfrom(1024)
                except socket.error:
                    break
                print("pkt %d bytes"%len(pkt))
                if from_ip=="127.0.0.1":
                    continue
                last_cmd_t=t
                cmd=pkt[0]
                if receive_mode=="NO_SIGNAL":
                    receive_mode="CONNECTED"
                if cmd=="P":
                    clauses=pkt[2:].split(",")
                    actions=[]
                    for clause in clauses: 
                        args=clause.split(" ")
                        chan=int(args[0])
                        if chan<0 or chan>NUM_PWM-1:
                            raise Exception("Invalid PWM channel")
                        pwm=int(args[1])
                        if pwm<0 or pwm>2000:
                            raise Exception("Invalid PWM value")
                        if len(args)>2:
                            delay=int(args[2])
                        else:
                            delay=None
                        if delay<0 or delay>1000:
                            raise Exception("Invalid delay")
                        if len(args)>3:
                            next_pwm=int(args[3])
                            if next_pwm<0 or next_pwm>2000:
                                raise Exception("Invalid next PWM value")
                        else:
                            next_pwm=None
                        if delay and next_pwm is None:
                            raise Exception("Missing next PWM value")
                    for chan,pwm,delay,next_pwm in actions:
                        if chan in delay_pwms:
                            continue
                        raspilot_usart.set_pwm(chan,pwm)
                        if delay:
                            delay_pwms[chan]=(val,t+delay,next_pwm)
            if last_cmd_t and t-last_cmd_t>NO_SIGNAL_DELAY and receive_mode!="NO_SIGNAL":
                signal_lost()
            dels=[]
            for chan,(pwm,sched_t,next_pwm) in delay_pwms.items():
                if t>=sched_t:
                    raspilot_usart.set_pwm(chan,next_pwm)
                    dels.append(chan)
            for chan in dels:
                del delay_pwms[chan]
            next_t=(t+20)*0.001
            t1=time.time()
            sleep_t=next_t-t1
            if sleep_t>0:
                time.sleep(sleep_t)
        except Exception as e:
            print("!"*80)
            print("ERROR")
            traceback.print_exc()
            signal_lost()
            time.sleep(5)
finally:
    signal_lost()