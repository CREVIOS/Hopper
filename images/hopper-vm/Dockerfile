FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 1. Base packages + SSH + supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openssh-server curl ca-certificates gnupg vim nano htop supervisor sudo \
        build-essential g++ gcc python3 python3-pip git && \
    mkdir -p /run/sshd /var/log/supervisor && \
    echo 'root:hopper' | chpasswd && \
    sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    # PAM's pam_loginuid writes a kernel audit record on every session start.
    # Inside K8s containers /proc/self/loginuid is restricted, sshd's audit
    # hook then fatal()s with "linux_audit_write_entry failed: Operation not
    # permitted" right after Connected!. Commenting the module out (the fix
    # documented in moby/moby#8244 + podman#13012) makes login proceed.
    sed -i '/pam_loginuid.so/s/^/#/g' /etc/pam.d/sshd

# 2. Install code-server via direct deb download
RUN curl -fL "https://github.com/coder/code-server/releases/download/v4.96.2/code-server_4.96.2_amd64.deb" \
        -o /tmp/code-server.deb && \
    dpkg -i /tmp/code-server.deb && \
    rm /tmp/code-server.deb

# 3. Cleanup
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# 4. code-server config
RUN mkdir -p /root/.config/code-server
COPY config/code-server-config.yaml /root/.config/code-server/config.yaml

# 5. Default VS Code settings
RUN mkdir -p /root/.local/share/code-server/User
COPY config/vscode-settings.json /root/.local/share/code-server/User/settings.json

# 6. supervisord config
RUN mkdir -p /etc/supervisor/conf.d
COPY config/supervisor.conf /etc/supervisor/conf.d/hopper.conf

# 7. Workspace directory
RUN mkdir -p /workspace

# 8. 'code' helper — prints a friendly message since code-server runs in the browser
RUN printf '#!/bin/sh\necho "Opening $@ in VS Code browser editor..."\necho "Files are shared — refresh the browser explorer to see changes."\n' \
    > /usr/local/bin/code && chmod +x /usr/local/bin/code

EXPOSE 22 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
