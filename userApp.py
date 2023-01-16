import boto3 #AWS SDK
import datetime #for timestamps
import sys #required for CLI arguments
import threading #for logging and alert checking threads
import time  #for sleep 
import requests # for calls to the namecheap API

# class to neatly store all three values fronm the /proc/loadavg file
class CPUsage:
    OneMinute = 0
    FiveMinutes = 0
    FifteenMinutes = 0

#class containing fields necessary for Namechaeap API
api = {
    'apiuser' : "",
    'apikey': "",
    'username' : "",
    'Command' : "",
    'ClientIp' : "",
    'SLD' : "",
    'TLD' : "",
    'HostName1' : "",
    'RecordType1' : "",
    'Address1' : "",
    'TTL1' : 0
    }

apiURL = ""
cpu = CPUsage()

LOG_BUCKET_NAME = 'cmp408LogBucket'
AUTO_SCALING_GROUP_NAME = "HybridScaler"
IS_CLOUD_LIVE = False
ELB_URL = "www.aws-fill-me-later.com"
LOCAL_IP = ""

def setupDNSAPI():
    global api
    global apiURL
    global LOCAL_IP
    file = open("./.APIcreds","r") # it is not good secure to leave API keys in code, thus they will be read from a file at runtime
    string = file.read()
    file.close()
    split =  string.split("\n") # split the string read from the file on a new line
    #assign the values of the global api object values read from hte file
    apiURL = split[0]
    api['apiuser'] = split[1]
    api['apikey'] = split[2]
    api['username'] = split[3]
    api['Command'] = split[4]
    api['ClientIp'] = split[5]
    LOCAL_IP = split[5]
    api['SLD'] = split[6]
    api['TLD'] = split[7]
    api['HostName1'] = split[8]
    api['RecordType1'] = split[9]
    api['Address1'] = split[10]
    api['TTL1'] = split[11]
    return

# this function will grab the LKMs decision on wether cloud functionality should be on
# 1 - on 
# 0 - off
def readDecision():
    dev = open("/dev/CPULED","r")
    decision = dev.read(2)
    dev.close()
    return decision

# this function will write the CPU usage percentage to the dev file, informing the LKM of it
def writeUtilisation(percentage):
    dev = open("/dev/CPULED","w")
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


def setDNStoAWSELB():
    print("sending the request to change the DNS record")
    global api
    global ELB_URL
    api["RecordType1"] = "CNAME"
    api["Address1"] = ELB_URL
    req = requests.post(url = apiURL, params = api)
    print(req.text)
    return

def setDNStoRPI():
    print("setting the DNS record back to the RPI")
    global api
    global LOCAL_IP
    api["RecordType1"] = "A"
    api["Address1"] = LOCAL_IP
    req = requests.post(url = apiURL, params = api)
    print(req.text)
    return 

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


def alertWatchingThread():
    print("starting to check for combined alert")
    CW = boto3.client('cloudwatch') #check w documentation
    
    #check the combined alarm (1 instance + lowCPU), can 'decomission' the cloud if triggered
    global IS_CLOUD_LIVE
    while IS_CLOUD_LIVE: #until the CloudOffAlarm triggers, signaling the cloud to be switched off
        print("could watching")
        response = CW.describe_alarms(AlarmNames=['CloudOffAlarm'])
        if response['StateValue'] == 'ALARM':
            #switch off auto scaled instances by setting desired capacity to 0
            scaler = boto3.client('autoscaling')
            response = scaler.set_desired_capacity(AutoScalingGroupName=AUTO_SCALING_GROUP_NAME,DesiredCapacity=0) 
            IS_CLOUD_LIVE = False # break out of loop and allow cloud to be started again at a later time
            setDNStoRPI() #regain the DNS record used
        time.sleep(180) # check every 3 minutes
    return


# this funtion will start the AWS cloud functionality of the system when instructed to do so by the LKM
def startCloud():
    global IS_CLOUD_LIVE
    print("Cloud is necessary")
    if  IS_CLOUD_LIVE:
        print("Cloud should be already running/starting")
        
    else:
        IS_CLOUD_LIVE = True
        print("Starting the cloud")
        setDNStoAWSELB() # change the DNS record to point to the Elastic Load Balancer
        # set the Auto Scaling Group's Desired capacity to 1 (from the resting state of 0)
        scaler = boto3.client('autoscaling')
        response = scaler.set_desired_capacity(AutoScalingGroupName=AUTO_SCALING_GROUP_NAME,DesiredCapacity=1)
        # start the alert watching thread, in order to terminate cloud when no longer necessary (1 instance live and low CPU% on it
     
    return

def main():
   
    args = sys.argv
    if (len(args) != 2):
        print("Usage: userApp.py [1,5,15]") # provide an error message if no arguments were specified (or too many were specified)
        return -1
    else:
        setupDNSAPI()
        actionLoop(int(args[1]))
   

if __name__ == "__main__":
    main()

