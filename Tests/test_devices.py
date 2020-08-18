import pytest
import CameraEvents
import datetime
try:
    #python 3+
    from configparser import ConfigParser
except:
    # Python 2.7
    from ConfigParser import ConfigParser

class dummy_mqtt(object):
    pass
    def publish(self,topic,payload):
        pass

def create_device():
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
    
    device = CameraEvents.DahuaDevice("Camera", device_cfg, client,basetopic,False)
    return device

def read_config():
    cp = ConfigParser()
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
    except Exception as ex:
        pass

def test_dahua_create():
    device = create_device()
    assert device is not None

def test_dahua_take_snapshot():
    device = create_device()
    device.host = 'cam-nvr.andc.nz'
    device.user = 'IOS'
    device.password = 'Dragon25'
    image = device.SnapshotImage(1,"Garage","message",nopublish=True)
    assert image is not None
    if len(image) > 600:
        sized = True
    assert sized is True

def test_dahua_search_images():
    device = create_device()
    device.host = 'cam-nvr.andc.nz'
    device.user = 'IOS'
    device.password = 'Dragon25'
    starttime = datetime.datetime.now() - datetime.timedelta(minutes=520)
    endtime = datetime.datetime.now()
    result = device.SearchImages(1, starttime,endtime,"",nopublish=True,message='')
    assert result is not None
    #if len(image) > 600:
    #    sized = True
    #assert sized is True


def test_dahua_search_clips():
    device = create_device()
    device.host = 'cam-nvr.andc.nz'
    device.user = 'IOS'
    device.password = 'Dragon25'
    starttime = datetime.datetime.now() - datetime.timedelta(minutes=520)
    endtime = datetime.datetime.now()
    result = device.SearchClips(1, starttime,endtime,"",nopublish=True,message='')
    assert result is not None
