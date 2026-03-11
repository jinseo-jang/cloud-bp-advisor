#!/bin/bash
set -e

PROJECT_ID=${GCP_PROJECT_ID:-$(gcloud config get-value project)}
REGION=${GCP_REGION:-"asia-northeast3"}
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/cba-repo"

echo "============================================================"
echo "🚀 Fast-track: Building and Deploying ONLY Sandbox Worker..."
echo "============================================================"

# 1. Build only sandbox worker
echo "Building Sandbox Worker image using Cloud Build..."
gcloud builds submit --tag ${REPO}/sandbox:latest ./sandbox-worker

# 2. Update the manifest explicitly for safety
echo "Updating k8s manifests..."
sed -i '' "s|image: .*/sandbox:.*|image: ${REPO}/sandbox:latest|g" k8s/sandbox-worker-deployment.yaml

# 3. Apply the deployment and restart rollout to ensure the change is picked up correctly
echo "Deploying Sandbox Worker to GKE..."
kubectl apply -f k8s/sandbox-worker-deployment.yaml -n cloud-bp-advisor
kubectl rollout restart deployment sandbox-worker -n cloud-bp-advisor

echo "✅ Sandbox Worker redeployed successfully."
