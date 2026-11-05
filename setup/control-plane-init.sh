#!/bin/bash
# ==============================================================================
# setup/control-plane-init.sh
# Run ONLY on the Control Plane node (t3.medium)
# ==============================================================================
set -euo pipefail

echo "===> [1/4] Running common setup (containerd + kubeadm)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/common-setup.sh"

echo "===> [2/4] Initializing Kubernetes Control Plane..."
# Detect primary private IP
PRIVATE_IP=$(hostname -I | awk '{print $1}')
echo "Binding kubeadm to private IP: ${PRIVATE_IP}"

sudo kubeadm init \
  --apiserver-advertise-address="${PRIVATE_IP}" \
  --pod-network-cidr=10.244.0.0/16 \
  --ignore-preflight-errors=NumCPU

echo "===> [3/4] Setting up kubeconfig for ubuntu user..."
mkdir -p "$HOME/.kube"
sudo cp -i /etc/kubernetes/admin.conf "$HOME/.kube/config"
sudo chown $(id -u):$(id -g) "$HOME/.kube/config"

echo "===> [4/4] Deploying Flannel CNI network plugin..."
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

echo ""
echo "======================================================================"
echo " CONTROL PLANE READY! RUN THE COMMAND BELOW ON WORKER NODES TO JOIN: "
echo "======================================================================"
kubeadm token create --print-join-command
echo "======================================================================"
echo ""
