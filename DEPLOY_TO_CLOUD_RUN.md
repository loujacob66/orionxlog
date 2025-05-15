# Deploying to Google Cloud Run

This guide will help you deploy this Streamlit app to Google Cloud Run using Docker and Google Container Registry (GCR).

---

## Prerequisites
- A Google Cloud account and project
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
- Docker installed and running
- Permissions to use Cloud Run and Container Registry in your Google Cloud project

---

## 1. Enable Required APIs

In the [Google Cloud Console](https://console.cloud.google.com/):
- Enable **Cloud Run Admin API**
- Enable **Container Registry API**

---

## 2. Authenticate with Google Cloud

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

---

## 3. Configure Docker to Use Google Credentials

```bash
gcloud auth configure-docker
gcloud config set project YOUR_PROJECT_ID
```

---

## 4. Build and Push the Docker Image for amd64

> **Note:** Cloud Run requires images built for `linux/amd64` (even on Apple Silicon/M1/M2 Macs).

> **Important:** Cloud Run requires your app to listen on port `8080`. The Dockerfile and Streamlit command must use this port:
>
> - In your Dockerfile, use `EXPOSE 8080` (not 8501)
> - The CMD should be:
>   ```dockerfile
>   CMD ["streamlit", "run", "app/Home.py", "--server.port=8080", "--server.address=0.0.0.0"]
>   ```

```bash
docker buildx build --platform linux/amd64 -t gcr.io/YOUR_PROJECT_ID/orionxlog --push .
```

---

## 5. Deploy to Cloud Run

```bash
gcloud run deploy orionxlog \
  --image gcr.io/YOUR_PROJECT_ID/orionxlog \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

- Change `--region` if you want to deploy to a different region.
- After deployment, Cloud Run will provide a public URL for your app.

---

## Troubleshooting

- **Image not found:** Make sure the image push step completed successfully and you used the correct project ID.
- **Architecture errors:** Always use the `--platform linux/amd64` flag when building on Apple Silicon.
- **Permissions errors:** Ensure your Google account has the necessary IAM roles (e.g., Storage Admin, Cloud Run Admin).

---

## References
- [Cloud Run Quickstart](https://cloud.google.com/run/docs/quickstarts/build-and-deploy)
- [Container Registry Quickstart](https://cloud.google.com/container-registry/docs/quickstart) 