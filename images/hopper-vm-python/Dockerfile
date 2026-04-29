FROM hopper/vm-ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git && \
    pip3 install --no-cache-dir numpy pandas scipy matplotlib jupyter && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
