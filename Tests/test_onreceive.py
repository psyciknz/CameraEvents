import pytest
import CameraEvents

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
    device_cfg["host"] =  "19.168.1.108"
    device_cfg["port"] = 80
    device_cfg["alerts"] = False
    client = dummy_mqtt()
    client.connected_flag = True

    basetopic = "CameraEvents"
    device = CameraEvents.DahuaDevice("Camera", device_cfg, client,basetopic)
    return device

def func(x):
    return x + 1

def test_answer():
    assert func(3) == 4

def test_answer2():
    assert func(3) == 4

def test_dahua_create():
    device = create_device()
    assert device is not None

def test_dahua_receive():
    device = create_device()
    data = "--myboundary\r\nContent-Length:37\r\nCode=VideoMotion;action=Start;index=1"
    device.OnReceive(data)
    
    assert device is not None

    