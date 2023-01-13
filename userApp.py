import sys #required for CLI arguments
import boto3 #AWS SDK
import time  #for sleep 
import datetime #for timestamps
import threading #for logging and alert checking threads

# class to neatly store all three values fronm the /proc/loadavg file
class CPUsage:
    OneMinute = 0
    FiveMinutes = 0
    FifteenMinutes = 0



cpu = CPUsage()
LOG_BUCKET_NAME = 'cmp408test'
AUTO_SCALING_GROUP_NAME = "MyScaler"
IsCloudLive = False



# this function will grab the LKMs decision on wether cloud functionality should be on
# 1 - on 
# 0 - off
def readDecision():
    dev = open("/dev/cloudLED","r")
    decision = dev.read(2)
    dev.close()
    return decision

# this function will write the CPU usage percentage to the dev file, informing the LKM of it
def writeUtilisation(percentage):
    dev = open("/dev/cloudLED","w")
    dev.write(percentage)
    dev.close
    return

# this function will use the /proc/loadavg to obtain the average load distributed over 1,5,15 minutes.
def getAverageLoad():
    proc = open("/proc/loadavg","r")
    loadString = proc.read() # the file should contain a space separated list, first 3 elements are of interest to us
    loadList = loadString.split(" ")
    
    cpu.OneMinute = loadList[0]
    cpu.FiveMinutes = loadList[1]
    cpu.FifteenMinutes = loadList[2]
    return

def actionLoop(mins):
    logThread = threading.Thread(target=writeLogDaemonThread,args=(),daemon=True) # create the logging thread as a daemon 
    print("started the log daemon")
    logThread.start()

    while(True):
        
        getAverageLoad()
        print("got average load!")
        ## Because of a last-minute bug found in the LKM, reported single-digit percentages would get treated as 10x the value
        ## This would result in 8% utilisation being treated as 80% utilisation and trigger cloud scaling.
        ## Values <10% will be reporeted to the kernel as 10%, as it bypasses the bug and will not affect the judgement
        ## Log files will contain the correct single-digit values. The bug could be corrected at a later time
        if mins == 1:
                if (float(cpu.OneMinute) < 0.10):
                    writeUtilisation(str(10))
                else:
                    writeUtilisation(str(int(float(cpu.OneMinute)* 100)))
                print("Wrote utilisation! " + str(int(float(cpu.OneMinute)* 100)))
        elif mins == 5:
                if(float(cpu.FiveMinutes) < 0.10):
                    writeUtilisation(str(10))
                else:
                    writeUtilisation(str(float(cpu.FiveMinutes) * 100))
                print("Wrote utilisation!")
        elif mins == 15:
                if(float(cpu.FifteenMinutes) < 0.10):
                    writeUtilisation(str(10))
                else:
                    writeUtilisation(str(float(cpu.FifteenMinutes) * 100))
                print("Wrote utilisation!")
        decision = readDecision()
        if ("1" in decision):
            print("do stuff \n")
            startCloud()
        else:
            print("don't do stuff")
        time.sleep(10) # only activcate once every 10 secs


def writeLogDaemonThread():
    time.sleep(10) # sleep for a few seconds at the start of the thread to allow the cpu object to populate 
    s3 = boto3.resource('s3')
    while 1: #until the program closes (it will not wait for this thread)
        ts = datetime.datetime.now() 
        tsa = ts.strftime("%m-%d-%Y-%H:%M:%S") #get the currend date and time in a printable way
        log = open(tsa,"w") # create the log file and make the first entry to it
        log.write(tsa + " 1M:" + str(cpu.OneMinute) +" 5M:"+str(float(cpu.FiveMinutes))+" 15M:"+str(cpu.FifteenMinutes)+"\n")
        log.close()
        #create the log file 
        for i in range(1,60): #for one hour
            time.sleep(60) # sleep for 60 seconds
            log = open(tsa,"a")
            log.write(datetime.datetime.now().strftime("%m-%d-%Y-%H:%M:%S") + " 1M:" + str(cpu.OneMinute) +" 5M:"+str(cpu.FiveMinutes)+" 15M:"+str(cpu.FifteenMinutes)+"\n")
            log.close() #append the current values to the log file
        #after this loop, the log should have entries for an hour, we can send this log off and start a new one
        log = open(tsa,'rb')
        s3.Bucket(LOG_BUCKET_NAME).put_object(Key=str(tsa+".log"),Body=log) # send over the log file to S3 bucket, create a new log file





# this funtion will start the AWS cloud functionality of the system when instructed to do so by the LKM
def startCloud():
    global IsCloudLive
    print("Cloud is necessary")
    if  IsCloudLive:
        print("Cloud should be already running/starting")
        
    else:
        IsCloudLive = True
        print("Starting the cloud")
        
        #make a request to namecheap API to forward the DNS record to AWS load balancer
        
        # set the Auto Scaling Group's Desired capacity to 1 (from the resting state of 0)
        scaler = boto3.client('autoscaling')
        response = scaler.set_desired_capacity(AutoScalingGroupName=AUTO_SCALING_GROUP_NAME,DesiredCapacity=1)
        # start the alert watching thread, in order to terminate cloud when no longer necessary (1 instance live and low CPU% on it)

    return

def main():
    IsCloudLive = False
    args = sys.argv
    if (len(args) != 2):
        print("Usage: userApp.py [1,5,15]") # provide an error message if no arguments were specified (or too many were specified)
        return -1
    else:
        print(int(args[1]))
        actionLoop(int(args[1]))
        
    # either start the loop from here, or use a thread to do it instead
       


if __name__ == "__main__":
    main()

