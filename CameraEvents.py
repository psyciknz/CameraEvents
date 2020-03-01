"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch
And https://github.com/SaWey/home-assistant-dahua-event
Author: PsycikNZ
"""


REQUIREMENTS = ['pycurl>=7']

import threading
import requests
import datetime
import re
import time
#import imageio
#from PIL import ImageFile
#from PIL import Image
#from io import BytesIO

#from slacker import Slacker
try:
    #python 3+
    from configparser import ConfigParser
except:
    # Python 2.7
    from ConfigParser import ConfigParser
import logging
import os
import socket
import pycurl
import json
import time
import paho.mqtt.client as paho   # pip install paho-mqtt
import base64

version = "0.1.3"
#ImageFile.LOAD_TRUNCATED_IMAGES = True
mqttc = paho.Client("CameraEvents-" + socket.gethostname(), clean_session=True)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)
_LOGGER.addHandler(ch)



def setup( config):
    """Set up Dahua event listener."""
    #config = config.get(DOMAIN)

    dahua_event = DahuaEventThread(
        None,
        None
    )

    def _start_dahua_event(_event):
        dahua_event.start()

    def _stop_dahua_event(_event):
        dahua_event.stopped.set()

    return True

class DahuaDevice():
    #EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=0&codes=%5B{events}%5D"
    EVENT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=%5B{events}%5D"
    CHANNEL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
    SNAPSHOT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/snapshot.cgi?channel={channel}"
    #SNAPSHOT_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/snapshot.cgi?chn={channel}"
    SNAPSHOT_EVENT = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attachFileProc&Flags[0]=Event&Events=%5B{events}%5D"
     #cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]    

    
    

    def __init__(self,  name, device_cfg, client, basetopic):
        if device_cfg["channels"]:
            self.channels = device_cfg["channels"]
        else:
            self.channels = {}
        self.Name = name
        self.CurlObj = None
        self.Connected = None
        self.Reconnect = None
        self.MQTTConnected = None
        self.user = device_cfg.get("user")
        self.password = device_cfg.get("pass")
        self.auth = device_cfg.get("auth")
        self.mqtt = device_cfg.get("mqtt")
        self.protocol  = device_cfg.get("protocol")
        self.host = device_cfg.get("host")
        self.port = device_cfg.get("port")
        self.alerts = device_cfg.get("alerts")
        self.token = device_cfg.get("token")
        self.client = client
        self.basetopic = basetopic
        self.snapshotoffset = device_cfg.get("snapshotoffset")

        #generate the event url
        self.url = self.EVENT_TEMPLATE.format(
            protocol=self.protocol,
            host=self.host,
            port=self.port,
            events=device_cfg.get("events")
            
        )
        
        
        self.isNVR = False
        try:
            # Get NVR parm, to get channel names if NVR
            self.isNVR = device_cfg.get("isNVR")

            if self.isNVR:
                #generate the channel url
                self.channelurl  = self.CHANNEL_TEMPLATE.format(
                    protocol=device_cfg.get("protocol"),
                    host=device_cfg.get("host"),
                    port=device_cfg.get("port")
                )
                self.snapshotevents = self.SNAPSHOT_EVENT.format(
                    protocol=self.protocol,
                    host=self.host,
                    port=self.port,
                    events=device_cfg.get("events")    
                )
                
                #RPCConnect(1)

                # get channel names here
                #table.ChannelTitle[0].Name=Garage
                _LOGGER.debug("Device " + name + " Getting channel ids: " + self.channelurl)
                response = requests.get(self.channelurl,auth=requests.auth.HTTPDigestAuth(self.user,self.password))
                for line in response.text.splitlines():
                    match = re.search(r'.\[(?P<index>[0-4])\]\..+\=(?P<channel>.+)',line)
                    if match:
                        _index = int(match.group("index"))
                        _channel = match.group("channel")
                        self.channels[_index] = _channel
            else:
                self.channels[0] = self.Name

            _LOGGER.info("Created Data Device: " + name)

        except Exception as e:
            _LOGGER.debug("Device " + name + " is not an NVR: " + str(e))
            _LOGGER.debug("Device " + name + " is not an NVR")


    def channelIsMine(self,channelname="",channelid=-1):
        channelidInt = -1
        if isinstance(channelid,str):
            channelidInt = int(channelid)
        else:
            channelidInt = channelid
        for channel in self.channels:
            if channelname is not None and channelname == self.channels[channel]:
                return channel
            elif channelidInt > -1 and channel == channelidInt:
                return channel

        return -1

 
    def SnapshotImage(self, channel, channelName, message,nopublish=False):
        """Takes a snap shot image for the specified channel
        channel (index number starts at 1)
        channelName if known for messaging
        message message to post
        nopublish True/False for posting to MQTT"""
        imageurl  = self.SNAPSHOT_TEMPLATE.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port,
                channel=channel
            )
        image = None
        _LOGGER.info("Snapshot Url: " + imageurl)
        try:
            if self.auth == "digest":
                image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPDigestAuth(self.user, self.password)).content
            else:
                image = requests.get(imageurl, stream=True,auth=requests.auth.HTTPBasicAuth(self.user, self.password)).content
        
            imagepayload = ""
            if image is not None and len(image) > 0:
                #fp = open("image.jpg", "wb")
                #fp.write(image) #r.text is the binary data for the PNG returned by that php script
                #fp.close()
                #construct image payload
                #{{ \"message\": \"Motion Detected: {0}\", \"imagebase64\": \"{1}\" }}"
                imagepayload = (base64.encodebytes(image)).decode("utf-8")
                msgpayload = json.dumps({"message":message,"imagebase64":imagepayload})
                #msgpayload = "{{ \"message\": \"{0}\", \"imagebase64\": \"{1}\" }}".format(message,imgpayload)
                
                if not nopublish:
                    self.client.publish(self.basetopic +"/{0}/Image".format(channelName),msgpayload)
        except Exception as ex:
            _LOGGER.error("Error sending image: " + str(ex))
            try:
                
                with open("default.png", 'rb') as thefile:
                    imagepayload = thefile.read().encode("base64")
                msgpayload = json.dumps({"message":"ERR:" + message, "imagebase64": imagepayload})
                if not nopublish:
                    self.client.publish(self.basetopic +"/{0}/Image".format(channelName),msgpayload)
            except:
                pass
        
       
        return image

    
    def SearchImages(self,channel,starttime, endtime, events,nopublish=True, message='',delay=0):
        """Searches for images for the channel
        channel is a numerical channel index (starts at 1)
        starttime is the start search time
        endtime is the end search time (or now)
        events is a list of event types"""
        #Create Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=factory.create 
        MEDIA_FINDER="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=factory.create"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}&condition.Types[0]=jpg&condition.Flag[0]=Event" \
            "&condition.Events[0]={events}"
        MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
            "&condition.Channel={channel}" + \
            "&condition.StartTime={starttime}&condition.EndTime={endtime}" + \
            "&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg"
            #&condition.Types=%5b0%5d=jpg" 
            #&condition.Types[0]=jpg
            #&condition.Flags[0]=Event&condition.Types[0]=jpg
            #&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg
            #%5B{events}%5D
        #MEDIA_START="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findFile&object={object}" + \
        #    "&condition.Channel={channel}" + \
        #    "&condition.StartTime=2019-12-05%2006:20:48&condition.EndTime=2019-12-05%2009:28:48&condition.Flags%5b0%5d=Event&condition.Types%5b0%5d=jpg"

        #Start Find
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=<objectId>&condition.Channel=<channel>&condition.StartTime=
        #  <start>&condition.EndTime=<end>&condition.Dirs[0]=<dir>&condition.Types[0]=<type>&condition.Flag[0]=<flag>&condition.E vents[0]=<event>
        #Start to find file wth the above condition. 
        # If start successfully, return true, else return false. 
        #  object : The object Id is got from interface in 10.1.1 
        #  Create condition.Channel: in which channel you want to find the file . 
        # condition.StartTime/condition.EndTime: the start/end time when recording. 
        # condition.Dirs: in which directories you want to find the file. It is an array. 
        #   The index starts from 0. The range of dir is {“/mnt/dvr/sda0”, “/mnt/dvr/sda1”}. 
        #   This condition can be omitted. If omitted, find files in all the directories. 
        # condition.Types: which types of the file you want to find. It is an array. 
        #   The index starts from 0. The range of type is {“dav”,“jpg”, “mp4”}. If omitted, 
        #   find files with all the types. 
        # condition.Flags: which flags of the file you want to find. It is an array. 
        #   The index starts from 0. The range of flag is {“Timing”, “Manual”, “Marker”, “Event”, “Mosaic”, “Cutout”}. 
        #   If omitted, find files with all the flags. 
        # condition.Event: by which event the record file is triggered. It is an array. 
        #   The index starts from 0. The range of event is {“AlarmLocal”, “VideoMotion”, “VideoLoss”, “VideoBlind”, “Traffic*”}. 
        #   This condition can be omitted. If omitted, find files of all the events. 
        #   Example: Find file in channel 1, in directory “/mnt/dvr/sda0",event type is "AlarmLocal" or 
        #   "VideoMotion", file type is “dav”, and time between 2011-1-1 12:00:00 and 2011-1-10 12:00:00 , 
        #   URL is: http://<ip>/cgi-bin/mediaFileFind.cgi?action=findFile&object=08137&condition.Channel=1&conditon.Dir[0]=”/mnt/dvr/sda0”& conditon.Event[0]=AlarmLocal&conditon.Event[1]=VideoMotion&condition.StartTime=2011-1-1%2012:00:00&condition.EndTi me=2011-1-10%2012:00:00

        #Find next File
        # http://<ip>/cgi-bin/mediaFileFind.cgi?action=findNextFile&object=<objectId>&count=<fileCount> Comment 
        MEDIA_NEXT="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={object}&count=50"
        
        MEDIA_LOADFILE="{protocol}://{host}:{port}/cgi-bin/RPC_Loadfile{file}"

        #Close Finder
        #http://<ip>/cgi-bin/mediaFileFind.cgi?action=close&object=<objectId> 
        MEDIA_CLOSE="{protocol}://{host}:{port}/cgi-bin/mediaFileFind.cgi?action=close&object={object}"

        if delay > 0:
            time.sleep(delay)

        finderurl  = MEDIA_FINDER.format(
                host=self.host,
                protocol=self.protocol,
                port  = self.port
            )
        objectId = ""
        cookies = {}
        s = requests.Session()
        if self.auth == "digest":
            auth = requests.auth.HTTPDigestAuth(self.user, self.password)
        else:
            auth = auth=requests.auth.HTTPBasicAuth(self.user, self.password)

        channelName = "Unknown"
        try:
            channelName = self.channels[channel-1]
        except:
            pass

        _LOGGER.info("SearchImages Finder Url: " + finderurl)
        try:
            #first request needs authentication
            if self.auth == "digest":
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content
            else:
                result = s.get(finderurl, stream=True,auth=auth,cookies=cookies).content

            #result = b'result=3021795080\r\n' 
            # Get the object id of the finder request, needed for subsequent searches
            objectId = self.ConvertLinesToDict(result.decode())["result"]
            _LOGGER.info("SearchImages:  Opened a search object: " + objectId)
            # perform a search.  Startime and endtime in the following format: 2011-1-1%2012:00:00
            finderurl = MEDIA_START.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId,channel=channel,
                starttime=starttime.strftime("%Y-%m-%d%%20%H:%M:%S"),
                endtime=endtime.strftime("%Y-%m-%d%%20%H:%M:%S")
                ,events="*")
            #finderurl = finderurl + requests.utils.quote("&condition.Types[0]=jpg")
            _LOGGER.info("SearchImages:  FinderURL: " + finderurl)
            result = s.get(finderurl, stream=True,auth=auth,cookies=cookies)
            if result.status_code == 200:
                finderurl = MEDIA_NEXT.format(host=self.host,protocol=self.protocol,port=self.port,object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies)
                mediaItem = {}
                if result.status_code == 200:
                    #start downloading the images.
                    mediaItem = self.ConvertLinesToDict(result.content.decode())
                    finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                        object=objectId)
                    
                    # Close the media find object
                    result = s.get(finderurl,auth=auth,cookies=cookies).content
                    #images = []
                    #imagesize = 0
                    #expectedsize = 0
                    image = None
                    _LOGGER.info("SearchImages: Found " + str(len(mediaItem)) + " images to process")
                    
                    filepath = ""

                    if type(mediaItem) is list:
                        for item in mediaItem:
                            filepath = item['FilePath']
                            _LOGGER.debug("SearchImages: Creating url for image: " + filepath)
                            loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                            _LOGGER.debug("SearchImages: LoadUrl: " + loadurl)
                            result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                            #result = s.get(loadurl,auth=auth,cookies=cookies)
                            image = self.ProcessSearchImage(item,result)
                            if image is not None:
                                break
                    else:
                        filepath = mediaItem['FilePath']
                        _LOGGER.debug("SearchImages: Creating url for image: " + filepath)
                        loadurl = MEDIA_LOADFILE.format(host=self.host,protocol=self.protocol,port=self.port,file=filepath)
                        _LOGGER.debug("SearchImages: LoadUrl: " + loadurl)
                        result = s.get(loadurl,auth=auth,cookies=cookies,stream=True)
                        #result = s.get(loadurl,auth=auth,cookies=cookies)
                        image = self.ProcessSearchImage(mediaItem,result)
                        
                    if image is not None:
                        imagepayload = (base64.encodebytes(image)).decode("utf-8")
                        msgpayload = json.dumps({"message":message,"imagebase64":imagepayload})
                        #msgpayload = "{{ \"message\": \"{0}\", \"imagebase64\": \"{1}\" }}".format(message,imgpayload)

                        if not nopublish:
                            _LOGGER.debug("SearchImages:  Publishing " + filepath)
                            self.client.publish(self.basetopic +"/{0}/Image".format(channelName),msgpayload)

                    #imageio.mimsave('movie.gif',images, duration=1.5)
                    #try:
                    #    slack = Slacker(self.token)
                    #    with open('movie.gif', 'rb') as f:
                    #        slack.files.upload(file_=BytesIO(f.read()),
                    #           title="Image'",
                    ##            channels=slack.channels.get_channel_id('camera'),
                    #            filetype='gif')
                    #except Exception as slackEx:
                    #    print(str(slackEx))
                    #'found': '3', 
                    #'items[0].Channel': '0', 
                    #'items[0].Cluster': '171757', 
                    #'items[0].Disk': '9',
                    #'items[0].EndTime': '2019-12-06 08:33:29', 
                    #'items[0].FilePath': '/mnt/dvr/2019-12-06...0][0].jpg', 
                    #'items[0].Length': '674816', 
                    #'items[0].Partition': '1', 
                    #'items[0].StartTime': '2019-12-06 08:33:29', 
                    #'items[0].Type': 'jpg',
                    #'items[0].VideoStream': 'Main',
                    #result = s.get(finderurl,auth=auth,cookies=cookies)
            else: #if result.status_code == 200:
                _LOGGER.info("SearchImages: Nothing Found for " + objectId)
        except Exception as ex:
            # if there's been an error and we've got an object id, close the finder.
            print("Error in search images: " + str(ex))
            if len(objectId) > 0:
                finderurl = MEDIA_CLOSE.format(host=self.host,protocol=self.protocol,port=self.port,
                object=objectId)
                result = s.get(finderurl,auth=auth,cookies=cookies).content
            pass

        return ""


    def ProcessSearchImage(self,item,result):
        #image = result.raw.read()
        #with open("1.jpg", 'wb') as f:
        #    for chunk in result:
        #        f.write(chunk)
        image = result.content
        imagesize = len(image)
        #image = result.content
        
        expectedsize =  int(item['Length'])
        expectedsize = int(float(expectedsize) * 0.65)
        _LOGGER.debug("SearchImages: Image " + item['FilePath'] + " Expected Size: (85%)" + str(expectedsize) 
            + "  Downloaded Size: " + str(imagesize))
        if imagesize >= expectedsize:
            #imagepayload = ""
            if image is not None and len(image) > 0:
                _LOGGER.debug("SearchImages:  This one meats size requirements: " + item['FilePath'])
                #fp = open("image.jpg", "wb")
                #fp.write(image) #r.text is the binary data for the PNG returned by that php script
                #fp.close()
                #construct image payload
                #{{ \"message\": \"Motion Detected: {0}\", \"imagebase64\": \"{1}\" }}"
                _LOGGER.info("SearchImages:   heres an image to post")
                return image
            else:
                _LOGGER.debug("SearchImages: Image too small: " + item['FilePath'] + " @  " + str(imagesize))
            #try:
            #    im = Image.open(BytesIO(result.content))
            #    im.resize((im.size[0] // 2, im.size[1] // 2), Image.ANTIALIAS) 
            #    images.append(im)
            #except Exception as imgEx:
            #    print(str(imgEx))
            #    pass
        #fp = open("image" + str(imagecount) + ".jpg", "wb")
        #fp.write(result.content) #r.text is the binary data for the PNG returned by that php script
        #fp.close()

    # Connected to camera
    def OnConnect(self):
        _LOGGER.debug("[{0}] OnConnect()".format(self.Name))
        self.Connected = True

    #disconnected from camera
    def OnDisconnect(self, reason):
        _LOGGER.debug("[{0}] OnDisconnect({1})".format(self.Name, reason))
        self.Connected = False

    #on receive data from camera.
    def OnReceive(self, data):
        #self.client.loop_forever()
        Data = data.decode("utf-8", errors="ignore")    
        _LOGGER.debug("[{0}]: {1}".format(self.Name, Data))

        crossData = ""

        for Line in Data.split("\r\n"):
            if Line == "HTTP/1.1 200 OK":
                self.OnConnect()

            if not Line.startswith("Code="):
                 continue
            
            Alarm = dict()
            Alarm["name"] = self.Name
            for KeyValue in Line.split(';'):
                Key, Value = KeyValue.split('=')
                Alarm[Key] = Value

            index =  int( Alarm["index"]         )
            if index in self.channels:
                Alarm["channel"] = self.channels[index]
            else:
                Alarm["channel"] = self.Name + ":" + str(index)

            #mqttc.connect(self.mqtt["IP"], int(self.mqtt["port"]), 60)
            if Alarm["Code"] == "VideoMotion":
                _LOGGER.info("Video Motion received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                if not self.client.connected_flag:
                        self.client.reconnect()
                if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"ON")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                    if self.alerts:
                        #possible new process:
                        #http://192.168.10.66/cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]
                        process = threading.Thread(target=self.SnapshotImage,args=(index+self.snapshotoffset,Alarm["channel"],"Motion Detected: {0}".format(Alarm["channel"])))
                        process.daemon = True                            # Daemonize thread
                        process.start()    
                else: #if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"ON")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                #    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" + Alarm["channel"] ,"OFF")
                #    _LOGGER.info("ReceiveData: calling search images") 
                #    starttime = datetime.datetime.now() - datetime.timedelta(minutes=5)
                #    endtime = datetime.datetime.now() 
                #    process2 = threading.Thread(target=self.SearchImages,args=(index+self.snapshotoffset,starttime,endtime,'',False,'Search Images VideoMotion',180))
                #    process2.daemon = True                            # Daemonize thread
                #    process2.start()
            elif Alarm["Code"] == "AlarmLocal":
                _LOGGER.info("Alarm Local received: "+  Alarm["name"] + " Index: " + str(index) + " Code: " + Alarm["Code"])
                # Start action reveived, turn alarm on.
                if Alarm["action"] == "Start":
                    if not self.client.connected_flag:
                        self.client.reconnect()
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" +  str(index) ,"ON")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                else: #if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["Code"] + "/" +  str(index) ,"OFF")
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
            elif Alarm["Code"] ==  "CrossRegionDetection" or Alarm["Code"] ==  "CrossLineDetection":
                if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                    regionText = Alarm["Code"]
                    try:

                        crossData = json.loads(Alarm["data"])
                        _LOGGER.info(Alarm["Code"] + " received: " + Alarm["data"] )
                        if "Direction" not in crossData:
                            direction = "unknown"                        
                        else:
                            direction = crossData["Direction"]

                        region = crossData["Name"]
                        object = crossData["Object"]["ObjectType"]
                        regionText = "{} With {} in {} direction for {} region".format(Alarm["Code"],object,direction,region)
                    except Exception as ivsExcept:
                        _LOGGER.error("Error getting IVS data: " + str(ivsExcept))
                        
                    self.client.publish(self.basetopic +"/IVS/" + Alarm["channel"] ,regionText)
                    if self.alerts:
                        #possible new process:
                        #http://192.168.10.66/cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[VideoMotion%2CVideoLoss]
                        process = threading.Thread(target=self.SnapshotImage,args=(index+self.snapshotoffset,Alarm["channel"],"IVS: {0}: {1}".format(Alarm["channel"],regionText)))
                        process.daemon = True                            # Daemonize thread
                        process.start() 
                else:   #if Alarm["action"] == "Start":
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                #    _LOGGER.info("ReceiveData: calling search images") 
                #    starttime = datetime.datetime.now() - datetime.timedelta(minutes=5)
                #    endtime = datetime.datetime.now() 
                #    process2 = threading.Thread(target=self.SearchImages,args=(index+self.snapshotoffset,starttime,endtime,'',False,'Search Images IVS',180))
                #    process2.daemon = True                            # Daemonize thread
                #    process2.start()       

            else: #if Alarm["Code"] == "VideoMotion": - unknown event
                _LOGGER.info("dahua_event_received: "+  Alarm["name"] + " Index: " + Alarm["channel"] + " Code: " + Alarm["Code"])
                if Alarm["action"] == "Start": 
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"ON")
                else:
                    self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/event" ,"OFF")
                self.client.publish(self.basetopic +"/" + Alarm["channel"] + "/" + Alarm["name"],Alarm["Code"])
                
            #2019-01-27 08:28:19,658 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,674 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,703 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossLineDetection
            #2019-01-27 08:28:19,729 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossRegionDetection
            #2019-01-27 08:28:19,743 - __main__ - INFO - dahua_event_received: NVR Index: NVR:0 Code: CrossLineDetection
            #mqttc.disconnect()
            #self.hass.bus.fire("dahua_event_received", Alarm)

    def ConvertLinesToDict(self,Data):
        results = dict()
        items = []
        currentIndex = ''
        indexCount = 0
        for Line in Data.split("\r\n"):
            if len(Line) == 0:
                if len(items) > 0:
                    items.append(results)
                    return items
                else:
                    return results
            if Line.find("[") > -1:
                if 'found' in results:
                    indexCount = int(results['found'])
                    results = dict()
                #array value found
                #items[0].Channel': '0'
                Item, Value = Line.split('=')
                Index, Key = Item.split(".")
                if currentIndex == '':
                    currentIndex = Index
                #Index= Index.replace("]","")
                if Index != currentIndex:
                    currentIndex = Index
                    items.append(results)
                    results = dict()
                results[Key] = Value.replace("\r\n","")
            else:

                for KeyValue in Line.split(';'):
                    Key, Value = KeyValue.split('=')
                    results[Key] = Value.replace("\r\n","")
        #else:
        #    for KeyValue in Data.split(';'):
        #        Key, Value = KeyValue.split('=')
        #        results[Key] = Value.replace("\r\n","")
        if len(items) > 0:
            return items
        else:
            return results



class DahuaEventThread(threading.Thread):
    """Connects to device and subscribes to events"""
    Devices = []
    NumActivePlayers = 0

    CurlMultiObj = pycurl.CurlMulti()
    NumCurlObjs = 0
	

    def __init__(self,  mqtt, cameras):
        """Construct a thread listening for events."""

        self.basetopic = mqtt["basetopic"]

        self.client = paho.Client("CameraEvents-" + socket.gethostname(), clean_session=True)
        if not mqtt["user"] is None and not mqtt["user"] == '':
            self.client.username_pw_set(mqtt["user"], mqtt["password"])
        self.client.on_connect = self.mqtt_on_connect
        self.client.on_disconnect = self.mqtt_on_disconnect
        self.client.message_callback_add(self.basetopic +"/+/picture",self.mqtt_on_picture_message)
        self.client.message_callback_add(self.basetopic +"/+/alerts",self.mqtt_on_alert_message)
        
        self.client.will_set(self.basetopic +"/$online",False,qos=0,retain=True)

        self.alerts = True

        for device_cfg in cameras:

            device = DahuaDevice(device_cfg.get("name"), device_cfg, self.client,self.basetopic)
            self.Devices.append(device)

            CurlObj = pycurl.Curl()
            device.CurlObj = CurlObj

            CurlObj.setopt(pycurl.URL, device.url)
            
            CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
            CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
            CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
            CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
            if device.auth == 'digest':
                CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
                CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (device.user, device.password))
            else:
                CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH)
                CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (device.user, device.password))
            CurlObj.setopt(pycurl.WRITEFUNCTION, device.OnReceive)

            self.CurlMultiObj.add_handle(CurlObj)
            self.NumCurlObjs += 1

            _LOGGER.debug("Added Dahua device at: %s", device.url)

        #connect to mqtt broker
        
        _LOGGER.debug("Connecting to MQTT Broker")
        self.client.connect(mqtt["IP"], int(mqtt["port"]), 60)
        
        _LOGGER.debug("Starting MQTT Loop")
        self.client.loop_start()

        threading.Thread.__init__(self)
        self.stopped = threading.Event() 


    def run(self):
        heartbeat = 0
        """Fetch events"""
        while 1:
            Ret, NumHandles = self.CurlMultiObj.perform()
            if Ret != pycurl.E_CALL_MULTI_PERFORM:
                break

        Ret = self.CurlMultiObj.select(1.0)
        while not self.stopped.isSet():
            # Sleeps to ease load on processor
            time.sleep(.05)
            heartbeat = heartbeat + 1
            if heartbeat % 1000 == 0:
                _LOGGER.debug("Heartbeat: " + str(datetime.datetime.now()))
                if not self.client.connected_flag:
                    self.client.reconnect()
                self.client.publish(self.basetopic +"/$heartbeat",str(datetime.datetime.now()))

            Ret, NumHandles = self.CurlMultiObj.perform()

            if NumHandles != self.NumCurlObjs:
                _, Success, Error = self.CurlMultiObj.info_read()

                for CurlObj in Success:
                    DahuaDevice = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Devices)), None)
                    if DahuaDevice.Reconnect:
                        _LOGGER.debug("Dahua Reconnect: %s", DahuaDevice.Name)
                        continue

                    DahuaDevice.OnDisconnect("Success")
                    DahuaDevice.Reconnect = time.time() + 5

                for CurlObj, ErrorNo, ErrorStr in Error:
                    DahuaDevice = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Devices)), None)
                    if DahuaDevice.Reconnect:
                        continue

                    DahuaDevice.OnDisconnect("{0} ({1})".format(ErrorStr, ErrorNo))
                    DahuaDevice.Reconnect = time.time() + 5

                for DahuaDevice in self.Devices:
                    if DahuaDevice.Reconnect and DahuaDevice.Reconnect < time.time():
                        self.CurlMultiObj.remove_handle(DahuaDevice.CurlObj)
                        self.CurlMultiObj.add_handle(DahuaDevice.CurlObj)
                        DahuaDevice.Reconnect = None
            #if Ret != pycurl.E_CALL_MULTI_PERFORM: break

    def mqtt_on_connect(self, client, userdata, flags, rc):
        if rc==0:
            _LOGGER.info("Connected to MQTT OK Returned code={0}".format(rc))
            self.client.connected_flag=True
            self.client.publish(self.basetopic +"/$online",True,qos=0,retain=True)
            self.client.publish(self.basetopic +"/$version",version)
            if self.alerts:
                state = "ON"
            else:
                state = "OFF"

            for device in self.Devices:
                device.alerts = state
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",state)
            self.client.subscribe(self.basetopic +"/+/picture")
            self.client.subscribe(self.basetopic +"/+/alerts")

            #self.client.subscribe("CameraEventsPy/alerts")
            
        else:
            _LOGGER.info("Camera : {0}: Bad mqtt connection Returned code={1}".format("self.Name",rc) )
            self.client.connected_flag=False

    def mqtt_on_disconnect(self, client, userdata, rc):
        logging.info("disconnecting reason  "  +str(rc))
        self.client.connected_flag=False
        

    def mqtt_on_picture_message(self,client, userdata, msg):

        #if msg.payload.decode() == "Hello world!":
        _LOGGER.info("Picture Msg Received: Topic:{0} Payload:{1}".format(msg.topic,msg.payload))
        msgchannel = msg.topic.split("/")[1]
        for device in self.Devices:
            channel = device.channelIsMine(channelid=msgchannel)
            if channel > -1:
                _LOGGER.debug("Found Camera: {0} channel: {1}: Name:{2}".format(device.Name,channel,device.channels[channel]))
                if msg.payload is not None:
                    try:
                        datestring = ''
                        datestring = (msg.payload).decode()
                        d = datetime.datetime.strptime(datestring, "%Y-%m-%dT%H:%M:%S")
                        #def SearchImages(self,channel,starttime, endtime, events):
                        device.SearchImages(channel+device.snapshotoffset,d,d + datetime.timedelta(minutes=2),'',nopublish=False,message="Snap Shot Image"  )
                    except Exception as searchI:
                        _LOGGER.warn("Error searching images: " + str(searchI))
                        d = None
                        pass
                else:
                    device.SnapshotImage(channel+device.snapshotoffset,msgchannel,"Snap Shot Image")
                break
    
                    
    def mqtt_on_alert_message(self,client, userdata, msg):
        if msg.payload == 'ON':
            newState = True
        else:
            newState = False

        deviceName = msg.topic.split('/')[1]
        _LOGGER.info("Camera: {0}: Msg Received: Topic:{1} Payload:{2}".format(deviceName,msg.topic,msg.payload))
        for device in self.Devices:
            #channel = self.Devices[device].channelIsMine("Garage")
            if device.Name == deviceName:
                device.alerts = newState
                _LOGGER.info("Turning Alerts {0}".format( newState))
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",msg.payload)

    def mqtt_on_cross_message(self,client, userdata, msg):
        if msg.payload == 'ON':
            newState = True
        else:
            newState = False

        deviceName = msg.topic.split('/')[1]
        _LOGGER.info("Camera: {0}: Msg Received: Topic:{1} Payload:{2}".format(deviceName,msg.topic,msg.payload))
        for device in self.Devices:
            #channel = self.Devices[device].channelIsMine("Garage")
            if device.Name == deviceName:
                device.alerts = newState
                _LOGGER.info("Turning Alerts {0}".format( newState))
                self.client.publish(self.basetopic +"/" + device.Name + "/alerts/state",msg.payload)

if __name__ == '__main__':

    cameras = []
    cp = ConfigParser()
    _LOGGER.info("Loading config")
    filename = {"config.ini","conf/config.ini"}
    dataset = cp.read(filename)

    try:
        if len(dataset) != 1:
            raise ValueError( "Failed to open/find all files")
        camera_items = cp.items( "Cameras" )
        for key, camera_key in camera_items:
            #do something with path
            camera_cp = cp.items(camera_key)
            camera = {}
            #temp = cp.get(camera_key,"host")
            camera["host"] = cp.get(camera_key,'host')
            camera["protocol"] = cp.get(camera_key,'protocol')
            camera["isNVR"] = cp.get(camera_key,'isNVR')
            camera["name"] = cp.get(camera_key,'name')
            camera["port"] = cp.getint(camera_key,'port')
            camera["user"] = cp.get(camera_key,'user')
            camera["pass"] = cp.get(camera_key,'pass')
            camera["auth"] = cp.get(camera_key,'auth')
            camera["events"] = cp.get(camera_key,'events')
            channels = {}
            if cp.has_option(camera_key,'channels'):
                try:
                    channellist = cp.get(camera_key,'channels').split('|')
                    for channel in channellist:
                        channelIndex = channel.split(':')[0]
                        channelName = channel.split(':')[1]
                        channels[int(channelIndex)] = channelName
                        
                except Exception as e:
                    _LOGGER.warning("Warning, No channel list in config (may be obtained from NVR):" + str(e))
                    channels = {}

            # added new snapshot offset section.
            if cp.has_option(camera_key,'snapshotoffset'):
                camera["snapshotoffset"] = cp.getint(camera_key,'snapshotoffset')
            else:
                camera["snapshotoffset"] = 0
            camera["channels"] = channels

            token = ""
            if cp.has_option("Slack","token"):
                token = cp.get("Slack","token")
                camera["token"] = token

            cameras.append(camera)

        mqtt = {}
        mqtt["IP"] = cp.get("MQTT Broker","IP")
        mqtt["port"] = cp.get("MQTT Broker","port")
        mqtt["basetopic"] = cp.get("MQTT Broker","BaseTopic")
        mqtt["user"] = cp.get("MQTT Broker","user",fallback=None)
        mqtt["password"] = cp.get("MQTT Broker","password",fallback=None)
        dahua_event = DahuaEventThread(mqtt,cameras)

        dahua_event.start()
    except Exception as ex:
        _LOGGER.error("Error starting:" + str(ex))

    

    

