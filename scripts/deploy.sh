#!/bin/bash
set -e
PROJECT_ID=${GCP_PROJECT_ID:-$(gcloud config get-value project)}
REGION=${GCP_REGION:-"asia-northeast3"}
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/cba-repo"

echo "============================================================"
echo "⚠️  PRE-FLIGHT CHECK: Infrastructure Required"
echo "Ensure you have provisioned the underlying infrastructure via"
echo "Terraform (in the /infrastructure folder) before running this."
echo "============================================================"
sleep 2

echo "Building images using Cloud Build (this may take a few minutes)..."
gcloud builds submit --tag ${REPO}/agent-backend:latest ./agent-backend > /tmp/backend_build.log 2>&1 &
PID2=$!
gcloud builds submit --tag ${REPO}/sandbox:latest ./sandbox-worker > /tmp/sandbox_build.log 2>&1 &
PID3=$!

wait $PID2
wait $PID3
echo "All builds completed."

echo "Updating k8s manifests..."
sed -i '' "s|image: .*/sandbox:.*|image: ${REPO}/sandbox:latest|g" k8s/sandbox-worker-deployment.yaml

echo "Getting GKE credentials..."
gcloud container clusters get-credentials cloud-bp-advisor-gke --region ${REGION}

# Deploy to GKE (Sandbox Worker Only)
# The agent-backend is now deployed to Cloud Run.
echo "Deploying Sandbox Worker to GKE..."
kubectl apply -k k8s/

# Deploy to Cloud Run (Agent Backend)
echo "Deploying Agent Backend to Cloud Run..."
gcloud run deploy agent-backend \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/cba-repo/agent-backend:latest \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},GCP_REGION=${REGION}"

echo "Deployment complete!"
# Cloud Run URL will be shown in the output of the command above.
