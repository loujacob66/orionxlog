# Deploying to Google Cloud Run

This guide will help you deploy this Streamlit app to Google Cloud Run using Docker and Google Container Registry (GCR).

---

## Development Workflow

You have three ways to run the application:

### 1. Pure Local Development (Recommended for Development)
```bash
# Run directly from local code
streamlit run app/Home.py
```
- Fastest development cycle
- Uses your local Python environment
- No Docker needed
- Best for day-to-day development

### 2. Local Docker Testing
```bash
# Test the containerized version locally
docker-compose up
```
- Tests the exact same container that will be deployed to Google Cloud
- Good for verifying Docker setup
- Slower than pure local development

### 3. Google Cloud Deployment
```bash
# Authenticate with Google Cloud (only needed once per session)
gcloud auth login
gcloud auth configure-docker

# Deploy to Cloud Run
./scripts/deploy-to-cloud-run.sh
```
- Deploys to production/staging environment
- Requires Google Cloud authentication

You can switch between these modes at any time. For development, we recommend using the pure local development method.

---

## Prerequisites
- A Google Cloud account and project
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
- Docker installed and running
- Permissions to use Cloud Run and Container Registry in your Google Cloud project

---

## Quick Deployment

The easiest way to deploy is using our automated deployment script:

```bash
./scripts/deploy-to-cloud-run.sh
```

This script will:
1. Check for required tools (gcloud, docker)
2. Verify Google Cloud authentication
3. Configure Docker with Google credentials
4. Build and push the Docker image
5. Deploy to Cloud Run

The script uses the following configuration:
- Project ID: `orionx-podcast-analysis`
- Region: `us-west2` (Los Angeles, optimized for West Coast users)
- Service Name: `orionx-podcast-analysis`

---

## Manual Deployment Steps

If you need to deploy manually or customize the deployment, follow these steps:

### 1. Enable Required APIs

In the [Google Cloud Console](https://console.cloud.google.com/):
- Enable **Cloud Run Admin API**
- Enable **Container Registry API**

### 2. Authenticate with Google Cloud

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 3. Configure Docker to Use Google Credentials

```bash
gcloud auth configure-docker
gcloud config set project YOUR_PROJECT_ID
```

### 4. Build and Push the Docker Image for amd64

> **Note:** Cloud Run requires images built for `linux/amd64` (even on Apple Silicon/M1/M2 Macs).

> **Important:** Cloud Run requires your app to listen on port `8080`. The Dockerfile and Streamlit command must use this port:
>
> - In your Dockerfile, use `EXPOSE 8080` (not 8501)
> - The CMD should be:
>   ```dockerfile
>   CMD ["streamlit", "run", "app/Home.py", "--server.port=8080", "--server.address=0.0.0.0"]
>   ```

```bash
docker buildx build --platform linux/amd64 -t gcr.io/YOUR_PROJECT_ID/orionx-podcast-analysis --push .
```

### 5. Deploy to Cloud Run

```bash
gcloud run deploy orionx-podcast-analysis \
  --image gcr.io/YOUR_PROJECT_ID/orionx-podcast-analysis \
  --platform managed \
  --region us-west2 \
  --allow-unauthenticated
```

---

## Troubleshooting

- **Image not found:** Make sure the image push step completed successfully and you used the correct project ID.
- **Architecture errors:** Always use the `--platform linux/amd64` flag when building on Apple Silicon.
- **Permissions errors:** Ensure your Google account has the necessary IAM roles (e.g., Storage Admin, Cloud Run Admin).
- **Script errors:** If the deployment script fails, check the error message and ensure you have all prerequisites installed and are properly authenticated.

---

## References
- [Cloud Run Quickstart](https://cloud.google.com/run/docs/quickstarts/build-and-deploy)
- [Container Registry Quickstart](https://cloud.google.com/container-registry/docs/quickstart) 

FROM python:3.11-slim

# ... rest of your Dockerfile ...

# Set Python version for gsutil
ENV CLOUDSDK_PYTHON=python3.11 

print("GOOGLE_APPLICATION_CREDENTIALS in env:", env.get("GOOGLE_APPLICATION_CREDENTIALS")) 