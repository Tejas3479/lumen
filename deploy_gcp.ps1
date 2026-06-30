# Lumen GCP Cloud Run Deployment Script
# Execute this script using: powershell -ExecutionPolicy Bypass -File .\deploy_gcp.ps1

$ProjectID = "lumen-hackathon-2"
$Region = "asia-south1"
$DBInstance = "lumen-db"
$RedisInstance = "lumen-redis"
$BucketName = "lumen-media-bucket-2"

# Add gcloud CLI to path for this session
$env:PATH += ";C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin"

Write-Host "=== Step 1: Configuring Project & Enabling GCP APIs ===" -ForegroundColor Cyan
gcloud config set project $ProjectID
gcloud services enable `
  run.googleapis.com `
  sqladmin.googleapis.com `
  redis.googleapis.com `
  storage.googleapis.com `
  artifactregistry.googleapis.com

Write-Host "=== Step 2: Creating Cloud SQL (PostgreSQL 15) ===" -ForegroundColor Cyan
gcloud sql instances create $DBInstance `
  --database-version=POSTGRES_15 `
  --tier=db-f1-micro `
  --region=$Region `
  --root-password=lumenrootpassword

gcloud sql databases create lumen --instance=$DBInstance
gcloud sql users create lumen --instance=$DBInstance --password=lumenpassword

$ConnectionName = gcloud sql instances describe $DBInstance --format="value(connectionName)"
Write-Host "Database Connection Name: $ConnectionName" -ForegroundColor Green

Write-Host "=== Step 3: Creating Cloud Memorystore (Redis) ===" -ForegroundColor Cyan
gcloud redis instances create $RedisInstance `
  --size=1 `
  --region=$Region `
  --tier=basic

$RedisIP = gcloud redis instances describe $RedisInstance --region=$Region --format="value(host)"
Write-Host "Memorystore Redis IP: $RedisIP" -ForegroundColor Green

Write-Host "=== Step 4: Creating Cloud Storage Bucket ===" -ForegroundColor Cyan
gsutil mb -p $ProjectID -c standard -l $Region gs://$BucketName
gsutil iam ch allUsers:objectViewer gs://$BucketName

Write-Host "=== Step 5: Setting Up Artifact Registry ===" -ForegroundColor Cyan
gcloud artifacts repositories create lumen --repository-format=docker --location=$Region
gcloud auth configure-docker "$Region-docker.pkg.dev"

Write-Host "=== Step 6: Building and Pushing Backend Docker Image ===" -ForegroundColor Cyan
cd backend
docker build -t "$Region-docker.pkg.dev/$ProjectID/lumen/backend:latest" .
docker push "$Region-docker.pkg.dev/$ProjectID/lumen/backend:latest"
cd ..

Write-Host "=== Step 7: Deploying Backend to Cloud Run ===" -ForegroundColor Cyan
# Temporary deployment to retrieve URL
gcloud run deploy lumen-backend `
  --image="$Region-docker.pkg.dev/$ProjectID/lumen/backend:latest" `
  --platform=managed `
  --region=$Region `
  --allow-unauthenticated `
  --add-cloudsql-instances=$ConnectionName `
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://lumen:lumenpassword@/lumen?host=/cloudsql/$ConnectionName,REDIS_URL=redis://$RedisIP:6379/0,SECRET_KEY=yoursecretkey123,ENVIRONMENT=production"

$BackendURL = gcloud run services describe lumen-backend --platform=managed --region=$Region --format="value(status.url)"
Write-Host "Backend URL: $BackendURL" -ForegroundColor Green

Write-Host "=== Step 8: Configuring & Pushing Frontend Docker Image ===" -ForegroundColor Cyan
# Replace placeholder BACKEND_URL in nginx.conf with actual Backend URL
(Get-Content frontend/nginx.conf) -replace 'http://BACKEND_URL/', $BackendURL | Set-Content frontend/nginx.conf

cd frontend
npm install
npm run build
docker build -f Dockerfile.prod -t "$Region-docker.pkg.dev/$ProjectID/lumen/frontend:latest" .
docker push "$Region-docker.pkg.dev/$ProjectID/lumen/frontend:latest"
cd ..

Write-Host "=== Step 9: Deploying Frontend to Cloud Run ===" -ForegroundColor Cyan
gcloud run deploy lumen-frontend `
  --image="$Region-docker.pkg.dev/$ProjectID/lumen/frontend:latest" `
  --platform=managed `
  --region=$Region `
  --allow-unauthenticated `
  --set-env-vars="VITE_API_URL=$BackendURL,VITE_WS_URL=$BackendURL"

$FrontendURL = gcloud run services describe lumen-frontend --platform=managed --region=$Region --format="value(status.url)"
Write-Host "Frontend URL: $FrontendURL" -ForegroundColor Green

Write-Host "=== Step 10: Updating Backend CORS configuration ===" -ForegroundColor Cyan
gcloud run services update lumen-backend `
  --platform=managed `
  --region=$Region `
  --update-env-vars="CORS_ORIGINS=$FrontendURL"

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Lumen Deployed Successfully on Google Cloud Platform!" -ForegroundColor Green
Write-Host "Live Frontend URL: $FrontendURL" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
