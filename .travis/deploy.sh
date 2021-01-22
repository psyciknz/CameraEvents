#!/usr/bin/env bash

set -e

if [ "$TRAVIS_PULL_REQUEST" == "true" ]; then
  echo "We should not deploy pull requests!"
  exit 1
fi

DOCKER_VERSION_TAG=$(grep -Po '(?<=version = \")[^\"]+' ./CameraEvents.py)
echo "Extracted Version number $DOCKER_VERSION_TAG"

if [ -z "$TRAVIS_TAG" ]; then
  DOCKER_IMAGE_TAG=$(if [ "$TRAVIS_BRANCH" == "master" ]; then echo "latest"; else echo "$TRAVIS_BRANCH-latest"; fi)
else
  DOCKER_IMAGE_TAG="$TRAVIS_TAG"
fi

echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

export DOCKER_IMAGE_TAG
export DOCKER_VERSION_TAG
export DOCKER_CLI_EXPERIMENTAL=enabled

docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
docker buildx create --use
#docker buildx build --progress plain --platform linux/amd64,linux/arm/v6,linux/arm/v7,linux/arm64/v8 -t "psyciknz/cameraevents:$DOCKER_IMAGE_TAG" -t "psyciknz/cameraevents:$DOCKER_VERSION_TAG"  --push .
docker buildx build --progress plain --platform linux/amd64 -t "psyciknz/cameraevents:$DOCKER_IMAGE_TAG" -t "psyciknz/cameraevents:$DOCKER_VERSION_TAG"  --push .
