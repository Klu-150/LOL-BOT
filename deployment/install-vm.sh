#!/usr/bin/env bash
set -euo pipefail
# Run on the newly provisioned Ubuntu VM, not on the user's Mac.
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
vm_arch="$(dpkg --print-architecture)"
vm_release="$(. /etc/os-release && echo "$VERSION_CODENAME")"
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${vm_release}
Components: stable
Architectures: ${vm_arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
if [ ! -e /swapfile ]; then
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
fi
sudo install -d -o "$(id -u)" -g "$(id -g)" /srv/league
printf 'VM Docker setup complete.\n'
