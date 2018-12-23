FROM __BASEIMAGE_ARCH__/python:2.7.15-jessie

__CROSS_COPY qemu/qemu-__QEMU_ARCH__-static /usr/bin/

# based on https://github.com/pfichtner/docker-mqttwarn

# install python libraries (TODO: any others?)
RUN pip install paho-mqtt requests ConfigParser pycurl

# build /opt/mqttwarn
RUN mkdir -p /opt/cameraevents
WORKDIR /opt/cameraevents

# add user mqttwarn to image
RUN groupadd -r cameraevents && useradd -r -g cameraevents cameraevents
RUN chown -R cameraevents /opt/cameraevents

# process run as mqttwarn user
USER cameraevents

# conf file from host
VOLUME ["/opt/cameraevents/conf"]

# set conf path
ENV CAMERAEVENTSINI="/opt/cameraevents/conf/config.ini"

# finally, copy the current code (ideally we'd copy only what we need, but it
#  is not clear what that is, yet)
COPY . /opt/cameraevents

# run process
CMD python CameraEvents.py

