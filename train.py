# -*- coding: utf-8 -*
"""
train simulation example

by Yuxiang Wu
Student ID: 996018
Date: 11/03/2017

Scenario:
    There is a train unloading dock. Trains arrive at the station as a Poisson process on average once every 10 hours. Each train takes between 3.5 and 4.5
    hours, uniformly at random, to unload. If the loading dock is busy, then trains wait in a first-come, first-served queue outside the loading dock for the
    currently unloading train to finish.
    
    Each train has a crew that, by union regulations, cannot work more than 12 hours at a time. When a train arrives at the station, the crew’s remaining work
    time is uniformly distributed at random between 6 and 11 hours. When a crew abandons their train at the end of their shift, they are said to have “hogged
    out”. A train whose crew has hogged out cannot be moved.
    
    So if a hogged-out train is at the front of the queue and the train in front finishes unloading, it cannot be moved into the loading dock until a replacement
    crew arrives (crews from other trains cannot be used).Furthermore, a train that is already in the loading dock cannot be unloaded in the absence of its crew.
    Once a train’s crew has hogged out, the arrival of a replacement crew takes between 2.5 and 3.5 hours, uniformly at random.the new crew’s 12-hour clock
    starts ticking as soon as they are called in for replacement
"""
import simpy
import random
import math
import os
from sys import argv



SIMU_TIME       = 72000 #simulation time set by user
TRAIN_ARRIVE    = 10    #average arrival rate of the train
Input_File      = False #whether the input is file
SUM_IN_SYSTEM   = 0
SUM_IN_SYSTEM_2 = 0
RUN_TIME        = 1

class Train(object):
    """ A train will arrive with a crew. Every time the crew hog out, if that train is in the dock, dock will stop unloading until new crew arrives."""
    def __init__(self, env, id, dock):
        self.env=env
        self.id=id
        #set train's arrival time
        self.arrive=env.now
        #train has not been hogged out yet, thus the number of hog out is 0
        self.hog_out_num=0
        #set how long will dock spend to unload this train
        self.unloading_time=get_unloading(id)
        #set crew's remaining work time
        self.remain_work=get_remain_work(id)
        self.process = env.process(self.working(dock))
        env.process(self.hog_out())
        
    #train arrives and waits in the queue. If the crew hogged out, it will wait for the new crew and won't be unloaded during that period
    def working(self, dock):
        global QUEUE_LENGTH
        global IDLE
        global BUSY
        global HOG_OUT
        global WAIT_IN_QUEUE
        global WAIT_IN_SYSTEM
        global SUM_QUEUE_LENGTH
        global last_event
        global is_idle
        global MAX_QUEUE_LEN
        global MAX_IN_SYSTEM
        global MAX_IN_QUEUE
        global hog_out_coll
        global RUN_TIME
        #Time 0.00: train 0 arrival for 4.45h of unloading,
        #crew 0 with 7.80h before hogout (Q=0)
        if RUN_TIME==1:
            print('Time %f: train %d arrival for %f h of unloading' % (self.arrive, self.id, self.unloading_time))
            print('\t\tcrew with %f h before hogout (Q=%d)' % (self.remain_work, QUEUE_LENGTH))
        #if there is no train before this train comes, the dock should be idle now and last event will be train's leaving
        if is_idle:
            #collect dock's idle time
            IDLE+=(self.env.now-last_event)
            is_idle=False
        #every time system calculates the sum of queue's length, time of last event will be refreshed
        SUM_QUEUE_LENGTH+=(QUEUE_LENGTH*(self.env.now-last_event))
        last_event=self.env.now
        #the train will request the dock once it arrives
        with dock.request() as req:
            QUEUE_LENGTH+=1
            if QUEUE_LENGTH>MAX_QUEUE_LEN:
                MAX_QUEUE_LEN=QUEUE_LENGTH
        #before train gets into the dock
            while True:
                start=self.env.now
                try:
                    yield req
                    self.remain_work-=(self.env.now-start)
                    if RUN_TIME==1:
                        print('Time %f: train %d entering dock for %fh of unloading' % (self.env.now, self.id, self.unloading_time))
                        print('\t\tCrew with %fh before hogout' % (self.remain_work))
                    WAIT_IN_QUEUE+=(self.env.now-self.arrive)
                    if (self.env.now-self.arrive) > MAX_IN_QUEUE:
                        MAX_IN_QUEUE=(self.env.now-self.arrive)
                    #go to the dock
                    break
                except simpy.Interrupt:
                    #hog out in the queue
                    #this interruption will only occurs when yield req is executed
                    next_crew=get_next_crew()
                    self.remain_work=12-next_crew
                    start=self.env.now
                    if RUN_TIME==1:
                        print('Time %f: train %d hogged out in queue' % (self.env.now, self.id))
                    results=yield req|self.env.timeout(next_crew)
                    #if train is in front of the queue before new crew arrives
                    #server's status will be changed to hog_out and the train still waits for the new crew
                    if req in results:
                        #train 34 crew 42 hasn't arrived yet,
                        #cannot enter dock (SERVER HOGGED)
                        if RUN_TIME==1:
                            print('Time %f: train %d crew hasn\'t arrived yet,' % (self.env.now, self.id))
                            print('\t\tcannot enter dock (SERVER HOGGED)')
                        #remain time for new crew's arrival
                        next_crew-=(self.env.now-start)
                        yield self.env.timeout(next_crew)
                        #train 34 replacement crew 42 arrives (SERVER UNHOGGED)
                        if RUN_TIME==1:
                            print('Time %f: train %d replacement crew arrives (SERVER UNHOGGED)' % (self.env.now, self.id))
                            print('Time %f: train %d entering dock for %fh of unloading' % (self.env.now, self.id, self.unloading_time))
                            print('\t\tCrew with %fh before hogout' % (self.remain_work))
                        if (self.env.now-self.arrive) > MAX_IN_QUEUE:
                            MAX_IN_QUEUE=(self.env.now-self.arrive)
                        WAIT_IN_QUEUE+=(self.env.now-self.arrive)
                        HOG_OUT+=next_crew
                        #since train is in the front of the queue, it will leave this in-queue phase
                        break
                #else it will go back to yield req
                
            #when train is in the dock
            #the circulation won't end until train has been unloaded
            dock_work=self.unloading_time
            SUM_QUEUE_LENGTH+=(QUEUE_LENGTH*(self.env.now-last_event))
            last_event=self.env.now
            #train goes to the dock
            QUEUE_LENGTH-=1
            while dock_work:
                try:
                    start=self.env.now
                    #interruption may happen here
                    yield self.env.timeout(dock_work)
                    dock_work=0
                except simpy.Interrupt:
                    #once the hog out happens
                    #calculate remaining work time of the train
                    if RUN_TIME<=2:
                        print('Time %f: train %d crew hogged out during service (SERVER HOGGED)' % (self.env.now, self.id))
                    dock_work-=(self.env.now-start)
                    start=self.env.now
                    #wait for new crew
                    yield self.env.timeout(get_next_crew())
                    if RUN_TIME<=2:
                        print('Time %f: train %d replacement crew arrives (SERVER UNHOGGED)' % (self.env.now, self.id))
                    #record the hog-out hour of dock
                    HOG_OUT+=(self.env.now-start)
            #record the busy hour of DOCK
            BUSY+=self.unloading_time
            #collect th time-in-system of this train
            WAIT_IN_SYSTEM+=(self.env.now-self.arrive)
            if (self.env.now-self.arrive) > MAX_IN_SYSTEM:
                MAX_IN_SYSTEM=(self.env.now-self.arrive)
            #if there is no train in the queue, the dock will start to be idle
            if QUEUE_LENGTH == 0:
                is_idle=True
            SUM_QUEUE_LENGTH+=(QUEUE_LENGTH*(self.env.now-last_event))
            last_event=self.env.now
            self.unloading_time=0
            if self.hog_out_num<=5:
                hog_out_coll[self.hog_out_num]+=1
            if RUN_TIME<=2:
                print('Time %f: train %d departing (Q=%d)' % (self.env.now, self.id, QUEUE_LENGTH))
    

    #hog-out process
    def hog_out(self):
        #first hog out will happen when the remaining work time runs out
        yield self.env.timeout(self.remain_work)
        if self.unloading_time > 0:
            self.hog_out_num+=1
            self.process.interrupt()
        while self.unloading_time:
            #after the first hog out, the train will be hogged out every 12 hours until it leaves
            yield self.env.timeout(12)
            if self.unloading_time > 0:
                self.hog_out_num+=1
                self.process.interrupt()

#set each train's arrival
def train_arrive(train_id):
    global TRAIN_ARRIVE
    global schedule
    if Input_File:
        schedule.seek(0,0)
        num_of_line=len(schedule.readlines())
        schedule.seek(0,0)
        str=schedule.read()
        if train_id==0:
            last_train_arrive=0
        elif train_id>=num_of_line:
            return 1024
        else:
            last_train_arrive=float(str.split()[3*train_id-3])
        return float(str.split()[3*train_id])-last_train_arrive
    else:
        u=random.uniform(0.000000000001, 1)
        return -1*math.log(u)*TRAIN_ARRIVE


#set each train's unloading time
def get_unloading(train_id):
    global MIN_UNLOAD_TIME
    global MAX_UNLOAD_TIME
    global schedule
    if Input_File:
        schedule.seek(0,0)
        str=schedule.read()
        return float(str.split()[3*train_id+1])
    else:
        return random.uniform(MIN_UNLOAD_TIME, MAX_UNLOAD_TIME)

#set each train's remain work time of the first crew
def get_remain_work(train_id):
    global MIN_REMAIN_WORK
    global MAX_REMAIN_WORK
    global schedule
    if Input_File:
        schedule.seek(0,0)
        str=schedule.read()
        return float(str.split()[3*train_id+2])
    else:
        return random.uniform(MIN_REMAIN_WORK, MAX_REMAIN_WORK)

#set when the new crew will arrive
def get_next_crew():
    global MIN_NEW_ARRIVAL
    global MAX_NEW_ARRIVAL
    global travel_time
    if Input_File:
        return float(travel_time.readline())
    else:
        return random.uniform(MIN_NEW_ARRIVAL, MAX_NEW_ARRIVAL)

#arrange different trains' arriving time
def Train_is_coming(env, dock):
    global id
    global SIMU_TIME
    while env.now<=SIMU_TIME:
        yield env.timeout(train_arrive(id))
        if env.now>SIMU_TIME:
            break
        t = Train(env, id, dock)
        id+=1


if len(argv) == 3:
    Input_File = False
    TRAIN_ARRIVE=float(argv[1])
    SIMU_TIME=float(argv[2])
    RUN_TIME=1
elif len(argv) == 4:
    if argv[1]=='-s':
        Input_File = True
        schedule   = open(os.getcwd()+'/'+argv[2], "r")
        travel_time= open(os.getcwd()+'/'+argv[3], "r")
        #get the number of lines in schedule.txt
        num_of_line=len(schedule.readlines())
        #go back to the begining of the file
        schedule.seek(0,0)
        #check the format of schedule.txt
        if len(schedule.readline().split()) != 3:
            print('format of first file is wrong! It should have three numbers each line')
            sys.exit(2)
        schedule.seek(0,0)
        #read all the numbers in schedule.txt
        str=schedule.read()
        #Set the last train's arriving time as SIMU_TIME since there won't be any new trains
        SIMU_TIME=float(str.split()[3*num_of_line-3])
    else:
        Input_File = False
        TRAIN_ARRIVE=float(argv[1])
        SIMU_TIME=float(argv[2])
        RUN_TIME=int(argv[3])
else:
    print('input format is wrong')
    sys.exit(2)





for x in range(RUN_TIME):
    env = simpy.Environment()
    dock= simpy.Resource(env, capacity=1)
    #initiate each statistics before run
    MAX_UNLOAD_TIME = 4.5   #maximum of train's unloading time
    MIN_UNLOAD_TIME = 3.5   #minimun of train's unloading time
    MAX_REMAIN_WORK = 11    #maximum of crew's remaining work time
    MIN_REMAIN_WORK = 6     #minimum of crew's remaining work time
    MAX_NEW_ARRIVAL = 3.5   #maximum of new crew's arrival time
    MIN_NEW_ARRIVAL = 2.5   #minimum of new crew's arrival time

    QUEUE_LENGTH    = 0     #length of  queue outside the loading dock
    SUM_QUEUE_LENGTH= 0     #sum of the queue length multiplies time
    MAX_QUEUE_LEN   = 0     #maximum of queue length

    WAIT_IN_QUEUE   = 0     #sum of every trains' time-in-queue time
    WAIT_IN_SYSTEM  = 0     #sum of every trains' time-in-system time
    MAX_IN_SYSTEM   = 0     #maximum of time-in-system
    MAX_IN_QUEUE    = 0     #maximum of time-in-queue


    IDLE            = 0     #idle time of the dock
    BUSY            = 0     #busy time of the dock
    HOG_OUT         = 0     #hog-out time of the dock

    last_event      = 0     #time of last event which might be train arriving, entering and leaving
    is_idle         = True  #whether the dock is idle
    id              = 0     #train's id
    

    #collect histogram of hog out
    hog_out_coll    = [0 for x in range(6)]

    i=env.process(Train_is_coming(env,dock))
    #collect sum of average wait-in-system in each run
    env.run()
    SUM_IN_SYSTEM   += (WAIT_IN_SYSTEM/id)
    #collect  square sum of average wait-in-system in each run
    SUM_IN_SYSTEM_2 += ((WAIT_IN_SYSTEM/id)**2)
    if RUN_TIME<=2:
        print('\nStatistics')
        print('----------')
        print('Total number of trains served: %d' % id)
        print('Average time-in-system per train: %fh' % (WAIT_IN_SYSTEM/id))
        print('Maximum time-in-system per train: %fh' % MAX_IN_SYSTEM)
        print('Dock idle percentage: %.2f%%' % (IDLE/last_event*100))
        print('Dock busy percentage: %.2f%%' % (BUSY/last_event*100))
        print('Dock hogged-out percentage: %.2f%%' % (HOG_OUT/last_event*100))
        print('Average time-in-queue over trains: %fh' % (WAIT_IN_QUEUE/id))
        print('Maximum number of trains in queue: %d' % (MAX_QUEUE_LEN))
        print('Histogram of hogout count per train:')
        for x in range(6):
            print('[%d]: %d' % (x, hog_out_coll[x]))

#average of mean time-in-system in different run
AVG_IN_SYSTEM=SUM_IN_SYSTEM/RUN_TIME
#variance
variance=(SUM_IN_SYSTEM_2-RUN_TIME*(AVG_IN_SYSTEM**2))
if RUN_TIME>2:
    print(variance)
    print(AVG_IN_SYSTEM-2.678*math.sqrt(variance/RUN_TIME))
    print(AVG_IN_SYSTEM+2.678*math.sqrt(variance/RUN_TIME))










if Input_File:
    schedule.close()
    travel_time.close()



