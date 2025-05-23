#!/bin/bash

# Exit on error
set -e

# Configuration
PROJECT_ID="orionx-podcast-analysis"
REGION="us-west2"
SERVICE_NAME="orionx-podcast-analysis"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment to Google Cloud Run...${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    exit 1
fi

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Ensure we're authenticated with Google Cloud
echo -e "${GREEN}Checking Google Cloud authentication...${NC}"
if ! gcloud auth print-access-token > /dev/null; then
    echo -e "${YELLOW}Not authenticated with Google Cloud.${NC}"
    echo -e "${YELLOW}Please run these commands first:${NC}"
    echo -e "  gcloud auth login"
    echo -e "  gcloud auth configure-docker"
    exit 1
fi

# Check if we're using a service account
if gcloud config get-value account | grep -q "gserviceaccount.com"; then
    echo -e "${YELLOW}Warning: You are authenticated as a service account.${NC}"
    echo -e "${YELLOW}For deployment, you should use your personal Google account.${NC}"
    echo -e "${YELLOW}Please run: gcloud auth login${NC}"
    exit 1
fi

# Set the project
echo -e "${GREEN}Setting Google Cloud project to ${PROJECT_ID}...${NC}"
gcloud config set project ${PROJECT_ID}

# Configure Docker to use Google credentials
echo -e "${GREEN}Configuring Docker with Google credentials...${NC}"
gcloud auth configure-docker

# Build and push the Docker image
echo -e "${GREEN}Building and pushing Docker image...${NC}"
docker buildx build --platform linux/amd64 -t ${IMAGE_NAME} --push .

# Deploy to Cloud Run
echo -e "${GREEN}Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --service-account storage-admin-sa@${PROJECT_ID}.iam.gserviceaccount.com \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
    --set-env-vars="BUCKET_NAME=orionxlog-backups" \
    --set-env-vars="ENVIRONMENT=cloud"

echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}Your service should be available at the URL shown above.${NC}" 