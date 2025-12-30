import logging
import pytest
import CameraEvents
import DahuaDevice
import datetime
try:
    #python 3+
    from configparser import ConfigParser
except:
    # Python 2.7
    from ConfigParser import ConfigParser

class dummy_mqtt(object):
    def __init__(self):
        self.payload = ''
        self.topic = ''
    
    def publish(self,topic,payload):
        self.payload = payload
        self.topic = topic
        pass

def create_device():
    
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add formatter to ch
    ch.setFormatter(formatter)
    _LOGGER.addHandler(ch)
    
    device_cfg = {}
    channels = {}
    device_cfg["channels"] = channels
    #device_cfg.set(["channels"]
    device_cfg["Name"] = "test"
    device_cfg["user"] =  "user"
    device_cfg["password"] = "pass"
    device_cfg["auth"] = "digest"
    device_cfg["mqtt"] = "localhsot"
    device_cfg["protocol"]  = "http"
    device_cfg["host"] =  "192.168.1.108"
    device_cfg["port"] = 80
    device_cfg["alerts"] = False
    device_cfg["snapshotoffset"] = 0
    client = dummy_mqtt()
    client.connected_flag = True

    basetopic = "CameraEvents"
    
    device = DahuaDevice.DahuaDevice("Camera", _LOGGER,device_cfg, client,basetopic,homebridge=False,publishImages=True)
    return device

def read_config():
    cp = ConfigParser()
    cameras = {}
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
            camera["user"] = cp.get(camera_key,'user')
            camera["password"] = cp.get(camera_key,'pass')
            camera["auth"] = cp.get(camera_key,'auth')
            cameras[camera_key] = camera
            
        return cameras
    except Exception as ex:
        pass

def test_dahua_create():
    device = create_device()
    assert device is not None

def test_dahua_take_snapshot():
    device = create_device()
    camera_items = read_config()
    if "NVR" in camera_items:
        device.host = camera_items["NVR"]["host"]
        device.user = camera_items["NVR"]["user"]
        device.password = camera_items["NVR"]["password"]
        device.auth = camera_items["NVR"]["auth"]
    
    image = device.SnapshotImage(1,"Garage","message",publishImages=False)
    assert image is not None
    if len(image) > 600:
        sized = True
    assert sized is True

def test_dahua_search_images():
    device = create_device()
    camera_items = read_config()
    if "NVR" in camera_items:
        device.host = camera_items["NVR"]["host"]
        device.user = camera_items["NVR"]["user"]
        device.password = camera_items["NVR"]["password"]
        device.auth = camera_items["NVR"]["auth"]
    starttime = datetime.datetime.now() - datetime.timedelta(minutes=520)
    endtime = datetime.datetime.now()
    result = device.SearchImages(1, starttime,endtime,"",publishImages=False,message='')
    assert result is not None
    #if len(image) > 600:
    #    sized = True
    #assert sized is True


def test_dahua_search_clips():
    device = create_device()
    camera_items = read_config()
    if "NVR" in camera_items:
        device.host = camera_items["NVR"]["host"]
        device.user = camera_items["NVR"]["user"]
        device.password = camera_items["NVR"]["password"]
        device.auth = camera_items["NVR"]["auth"]
        
    starttime = datetime.datetime.now() - datetime.timedelta(minutes=520)
    endtime = datetime.datetime.now()
    result = device.SearchClips(1, starttime,endtime,"",message='')
    assert result is not None
