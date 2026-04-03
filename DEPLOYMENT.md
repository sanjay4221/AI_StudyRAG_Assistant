# ☁️ Azure Deployment Guide — StudyRAG

This guide documents the complete deployment of StudyRAG to Azure Container Apps with Neon PostgreSQL.

---

## Architecture Overview

```
GitHub → Docker Build → Azure Container Registry → Azure Container Apps
                                                           │
                                              Neon PostgreSQL (cloud DB)
                                              ChromaDB (local /tmp)
                                              Azure Files (uploads — optional)
```

---

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
- Azure account with active subscription
- [Neon account](https://neon.tech) (free tier)
- [Groq API key](https://console.groq.com) (free tier)

---

## Step 1 — Azure Login

```powershell
az login
```

---

## Step 2 — Set Variables

```powershell
$RESOURCE_GROUP = "studyrag-rg"
$LOCATION       = "australiaeast"
$REGISTRY_NAME  = "studyragregistry"
$APP_NAME       = "studyrag-app"
$ENVIRONMENT    = "studyrag-env"
```

---

## Step 3 — Create Resource Group

```powershell
az group create --name $RESOURCE_GROUP --location $LOCATION
```

---

## Step 4 — Create Container Registry

```powershell
# Register provider if needed
az provider register --namespace Microsoft.ContainerRegistry --wait

az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $REGISTRY_NAME `
  --sku Basic `
  --admin-enabled true
```

---

## Step 5 — Build and Push Docker Image

```powershell
# Build
docker build -t student-rag-studyrag:latest .

# Tag
docker tag student-rag-studyrag:latest $REGISTRY_NAME.azurecr.io/studyrag:latest

# Login to registry
az acr login --name $REGISTRY_NAME

# Push
docker push $REGISTRY_NAME.azurecr.io/studyrag:latest
```

---

## Step 6 — Create Container Apps Environment

```powershell
# Register providers
az provider register -n Microsoft.App --wait
az provider register -n Microsoft.OperationalInsights --wait

az containerapp env create `
  --name $ENVIRONMENT `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION
```

---

## Step 7 — Set Up Neon PostgreSQL

1. Go to [neon.tech](https://neon.tech) and create a free account
2. Create a new project (select region closest to your Azure region)
3. Copy the connection string from the dashboard:
   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```

---

## Step 8 — Get Registry Credentials

```powershell
$REGISTRY_PASSWORD = $(az acr credential show `
  --name $REGISTRY_NAME `
  --query "passwords[0].value" `
  --output tsv)
```

---

## Step 9 — Create Container App

```powershell
az containerapp create `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --environment $ENVIRONMENT `
  --image $REGISTRY_NAME.azurecr.io/studyrag:latest `
  --registry-server $REGISTRY_NAME.azurecr.io `
  --registry-username $REGISTRY_NAME `
  --registry-password $REGISTRY_PASSWORD `
  --target-port 8000 `
  --ingress external `
  --min-replicas 0 `
  --max-replicas 1 `
  --cpu 1 `
  --memory 2Gi `
  --env-vars `
    GROQ_API_KEY=your_groq_key_here `
    JWT_SECRET_KEY=your_jwt_secret_here `
    DATABASE_URL=your_neon_connection_string_here `
    VECTORSTORE_DIR=/tmp/vectorstore `
    UPLOAD_DIR=/tmp/uploads `
    DATA_DIR=/tmp/data
```

---

## Step 10 — Verify Deployment

```powershell
az containerapp show `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --query "properties.configuration.ingress.fqdn"
```

Visit the URL to confirm the app is running.

---

## Updating the App

After making code changes:

```powershell
# Rebuild and push
docker build -t student-rag-studyrag:latest .
docker tag student-rag-studyrag:latest $REGISTRY_NAME.azurecr.io/studyrag:latest
az acr login --name $REGISTRY_NAME
docker push $REGISTRY_NAME.azurecr.io/studyrag:latest

# Create new revision (pulls latest image)
az containerapp revision copy `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` || Groq API key |
| `JWT_SECRET_KEY` || Fixed secret for JWT (never change in production) |
| `DATABASE_URL` || Neon PostgreSQL connection string |
| `VECTORSTORE_DIR` || `/tmp/vectorstore` (local container path) |
| `UPLOAD_DIR` || `/tmp/uploads` (local container path) |
| `DATA_DIR` || `/tmp/data` |

---

## Important Notes

### Why `/tmp` for vectorstore and uploads?
Azure Files SMB shares do not support SQLite file locking, which ChromaDB requires. Using local `/tmp` paths avoids this issue. Note that `/tmp` data is **ephemeral** — it resets on container restart. For production, use a managed vector database like Pinecone or Qdrant.

### Why Neon instead of Azure PostgreSQL?
Neon's free tier provides a fully managed PostgreSQL instance at no cost, whereas Azure PostgreSQL Flexible Server has no free tier (~$30/month minimum).

### Why Max Replicas = 1?
ChromaDB running locally cannot be shared across multiple container instances. Setting max replicas to 1 prevents data inconsistency. For horizontal scaling, migrate ChromaDB to a managed vector database.

### Scale to Zero
Setting `--min-replicas 0` means the container shuts down when idle, saving compute costs. The first request after idle takes ~30 seconds to cold start — acceptable for a feedback/testing phase.

---

## Making a User Admin

Connect to the running container console and run:

```python
python -c "
import os, sys
sys.path.insert(0, '/app/backend')
from db.database import SessionLocal
from db.models import User
db = SessionLocal()
user = db.query(User).filter(User.email == 'your@email.com').first()
if user:
    user.is_admin = True
    db.commit()
    print('Done! Admin granted to:', user.email)
db.close()
"
```

---

## Cost Estimate (Australia East)

| Resource | Monthly Cost |
|----------|-------------|
| Container Apps (consumption, scale-to-zero) | ~$1–5 |
| Container Registry (Basic) | ~$5 |
| Log Analytics workspace | ~$1–2 |
| Neon PostgreSQL (free tier) | $0 |
| **Total** | **~$7–12/month** |

With Azure's $200 free credits, this runs for approximately **16–28 months**.
