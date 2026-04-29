FROM hopper/vm-ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential cmake gdb valgrind git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
