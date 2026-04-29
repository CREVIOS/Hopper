FROM hopper/vm-ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      openjdk-21-jdk maven git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
