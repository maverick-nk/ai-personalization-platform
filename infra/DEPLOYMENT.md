# Deployment Guide

Step-by-step instructions for spinning up the **dev** and **prod** environments on GCP using Terraform and Kubernetes.

---

## Prerequisites

### Tools

Install these before starting:

| Tool | Minimum version | Install |
|---|---|---|
| `terraform` | 1.7 | [developer.hashicorp.com/terraform](https://developer.hashicorp.com/terraform/install) |
| `gcloud` CLI | latest | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| `kubectl` | 1.29 | `gcloud components install kubectl` |
| `helm` | 3.14 | [helm.sh/docs/intro/install](https://helm.sh/docs/intro/install/) |
| `docker` | 24 | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |

After installing or updating `gcloud`, run:

```bash
gcloud components update
gcloud components install gke-gcloud-auth-plugin kubectl
```

### GCP project

You need a GCP project with billing enabled. All commands below use `$PROJECT_ID` and `$REGION` — set them once and verify before running any command:

```bash
export PROJECT_ID=your-gcp-project-id   # e.g. my-project-123456
export REGION=us-central1

# Verify both are set — if either prints blank, stop and re-export before continuing.
echo "PROJECT_ID: $PROJECT_ID"
echo "REGION:     $REGION"
```

> **Common failure:** `gcloud storage buckets create` returns `400 The specified location constraint is not valid` when `$REGION` is empty. The command sends `--location=` (empty string) and GCS rejects it. Always run the `echo` check above in each new terminal session before proceeding.

---

## Part 1 — One-time GCP bootstrap (project owner, run once)

These steps create the IAM principals and Terraform state buckets. Run them as a project owner. You will not need owner access again after this.

### 1.1 Enable required APIs

```bash
gcloud services enable \
  container.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  servicenetworking.googleapis.com \
  --project=$PROJECT_ID
```

### 1.2 Create Terraform state buckets

One bucket per environment. These must exist before `terraform init`.

```bash
gcloud storage buckets create gs://${PROJECT_ID}-tf-state-dev \
  --location=$REGION --project=$PROJECT_ID

gcloud storage buckets create gs://${PROJECT_ID}-tf-state-prod \
  --location=$REGION --project=$PROJECT_ID

# Enable versioning so you can recover from accidental state corruption
gcloud storage buckets update gs://${PROJECT_ID}-tf-state-dev --versioning
gcloud storage buckets update gs://${PROJECT_ID}-tf-state-prod --versioning
```

### 1.3 Create the Terraform service account

```bash
gcloud iam service-accounts create terraform-operator \
  --display-name "Terraform Operator" \
  --project=$PROJECT_ID
```

Bind the required roles. Each grants full control of one GCP service — none grant project-wide access or the ability to modify IAM policy:

```bash
for ROLE in \
  roles/container.admin \
  roles/cloudsql.admin \
  roles/redis.admin \
  roles/artifactregistry.admin \
  roles/compute.networkAdmin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:terraform-operator@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=$ROLE
done
```

**Why each role:** `container.admin` — create/delete GKE clusters and node pools (no sub-admin predefined role for cluster creation exists). `cloudsql.admin` — create the instance, databases, and users. `redis.admin` — create the Memorystore instance. `artifactregistry.admin` — create the Docker repository (`artifactregistry.repoAdmin` can only manage content in existing repos). `compute.networkAdmin` — create VPC, subnets, Cloud NAT, firewall rules, and reserve static IPs.

**What this SA cannot do:** modify billing, change project-level IAM policy, create non-GKE Compute VMs, read data inside Cloud SQL or Redis, push/pull Docker images, or delete the GCP project.

Grant storage access only on the specific buckets (not project-wide):

```bash
for BUCKET in \
  gs://${PROJECT_ID}-tf-state-dev \
  gs://${PROJECT_ID}-tf-state-prod; do
  gcloud storage buckets add-iam-policy-binding $BUCKET \
    --member="serviceAccount:terraform-operator@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/storage.admin
done
```

Download the key and configure it locally:

```bash
gcloud iam service-accounts keys create ~/terraform-sa-key.json \
  --iam-account=terraform-operator@${PROJECT_ID}.iam.gserviceaccount.com

export GOOGLE_APPLICATION_CREDENTIALS=~/terraform-sa-key.json
```

### 1.4 Create Workload Identity service accounts

These GCP service accounts are bound to Kubernetes service accounts so pods can access GCS without credential files. Three services need GCS access; two do not.

```bash
for SA in feature-pipeline-sa model-training-sa mlflow-sa; do
  gcloud iam service-accounts create $SA \
    --display-name "$SA" \
    --project=$PROJECT_ID
done
```

**Why each SA needs what it needs:**

---

**`feature-pipeline-sa`** — runs the Flink job. Needs `storage.objectAdmin` on the parquet bucket.

Flink does four distinct things with GCS:
- Writes Parquet files continuously (`storage.objects.create`)
- Reads checkpoints on job recovery after a spot preemption (`storage.objects.get`)
- Lists the checkpoint directory to find the latest savepoint (`storage.objects.list`)
- Deletes expired checkpoints when the retention limit is exceeded (`storage.objects.delete`)

All four are required. The predefined GCS roles have no middle ground between `storage.objectViewer` (list + get, no write) and `storage.objectAdmin` (list + get + create + delete). `objectAdmin` also includes `getIamPolicy`/`setIamPolicy` on objects, but these are inert because Terraform sets `uniform_bucket_level_access = true` on the bucket — GCS rejects per-object IAM operations when this flag is on.

**Cannot do:** access any other bucket, modify bucket-level IAM, access Cloud SQL or Redis.

---

**`model-training-sa`** — runs the nightly training CronJob. Needs `storage.objectViewer` on the parquet bucket **only**.

`train.py` reads Parquet partitions (`storage.objects.get` + `storage.objects.list`) and that is all it does with GCS. Model artifacts (the trained model, `feature_schema.json`) are uploaded via the MLflow HTTP API using the `mlflow-artifacts:/` proxy scheme — the training pod never touches the MLflow artifacts bucket directly. The MLflow server (using `mlflow-sa`) handles those writes.

`storage.objectViewer` = list + get. Exactly the minimum.

**Cannot do:** write or delete any GCS object, access the MLflow artifacts bucket at all.

---

**`mlflow-sa`** — runs the MLflow tracking server with `--serve-artifacts`. Needs `storage.objectAdmin` on the MLflow artifacts bucket **only**.

The `--serve-artifacts` flag makes the MLflow server proxy all artifact reads and writes. No other pod writes directly to the MLflow artifacts bucket:
- Training job uploads artifacts → MLflow REST API → `mlflow-sa` → GCS (`storage.objects.create`)
- Inference API downloads models → MLflow REST API → `mlflow-sa` → GCS (`storage.objects.get`)
- MLflow artifact browser lists runs → `mlflow-sa` → GCS (`storage.objects.list`)
- `mlflow gc` (garbage-collect deleted runs) → `mlflow-sa` → GCS (`storage.objects.delete`)

Same predefined role gap as `feature-pipeline-sa`: create + get + list + delete together only appear in `storage.objectAdmin`. The IAM-on-objects permissions are again inert due to uniform bucket-level access.

**Cannot do:** access the parquet bucket, access Cloud SQL directly (connects via private IP using the DB URL in a Kubernetes secret), modify any IAM policy.

---

Grant the permissions. Run these after `terraform apply` for each environment — the buckets must exist first:

```bash
for ENV in dev prod; do
  # feature-pipeline: write Parquet + manage Flink checkpoints
  gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-parquet-${ENV} \
    --member="serviceAccount:feature-pipeline-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/storage.objectAdmin

  # model-training: read Parquet partitions for training input (no write needed)
  gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-parquet-${ENV} \
    --member="serviceAccount:model-training-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/storage.objectViewer

  # mlflow: proxy all artifact reads and writes (--serve-artifacts mode)
  gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-mlflow-artifacts-${ENV} \
    --member="serviceAccount:mlflow-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/storage.objectAdmin
done
```

### 1.5 Create the CI/CD image-push service account

**`cicd-image-pusher`** — used by GitHub Actions to push Docker images. Needs `roles/artifactregistry.writer` scoped to the single `personalization` repository.

`artifactregistry.writer` grants:
- `artifactregistry.repositories.uploadArtifacts` — push image layers and manifests
- `artifactregistry.repositories.downloadArtifacts` — pull base layers during multi-stage builds
- `artifactregistry.repositories.get` — verify the repository exists before pushing

It does **not** grant:
- `artifactregistry.repositories.create` — Terraform creates the repository; CI cannot
- `artifactregistry.repositories.delete` — CI cannot destroy the registry
- `artifactregistry.tags.delete` — CI cannot remove existing image tags

The binding is at the repository level (`personalization`), not the project level, so the SA cannot access any other Artifact Registry repository in the project.

```bash
gcloud iam service-accounts create cicd-image-pusher \
  --display-name "CI/CD Image Pusher" \
  --project=$PROJECT_ID

gcloud artifacts repositories add-iam-policy-binding personalization \
  --location=$REGION \
  --member="serviceAccount:cicd-image-pusher@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.writer \
  --project=$PROJECT_ID
```

---

## Part 2 — Terraform: provision infrastructure

Both environments use the same modules. The only difference is sizing (zonal vs regional GKE, `db-f1-micro` vs `db-g1-small`, etc.).

### 2.1 Fill in `terraform.tfvars`

Edit both files and replace the placeholder:

**`infra/terraform/environments/dev/terraform.tfvars`**
```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"
zone       = "us-central1-a"
```

**`infra/terraform/environments/prod/terraform.tfvars`**
```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"
```

### 2.2 Update the backend bucket names

Edit the `bucket` field in each backend file to match your project:

- `infra/terraform/environments/dev/backend.tf` → `bucket = "your-project-id-tf-state-dev"`
- `infra/terraform/environments/prod/backend.tf` → `bucket = "your-project-id-tf-state-prod"`

### 2.3 Apply dev

```bash
cd infra/terraform/environments/dev
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Save the outputs — you will need them for the Kubernetes steps:

```bash
terraform output gke_cluster_name
terraform output repository_url
terraform output parquet_bucket
terraform output mlflow_artifacts_bucket
terraform output redis_host
terraform output redis_port
terraform output cloud_sql_private_ip
terraform output -raw privacy_db_url   # sensitive
terraform output -raw mlflow_db_url    # sensitive
```

### 2.4 Apply prod

```bash
cd infra/terraform/environments/prod
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Prod has `deletion_protection = true` on the Cloud SQL instance and the GKE cluster. To tear it down you must first disable that flag manually.

---

## Part 3 — Bind Workload Identity

After the GKE cluster exists, bind each GCP service account to its Kubernetes counterpart. Run once per environment, substituting the correct namespace.

```bash
# Get cluster credentials first (see Part 4, Step 4.1)
for SA_PAIR in \
  "feature-pipeline-sa:feature-pipeline" \
  "model-training-sa:model-training" \
  "mlflow-sa:mlflow"; do
  GCP_SA=$(echo $SA_PAIR | cut -d: -f1)
  KSA=$(echo $SA_PAIR | cut -d: -f2)
  gcloud iam service-accounts add-iam-policy-binding \
    ${GCP_SA}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role=roles/iam.workloadIdentityUser \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[ai-personalization-platform/${KSA}]" \
    --project=$PROJECT_ID
done
```

---

## Part 4 — Kubernetes: deploy the platform

Run these steps after `terraform apply` completes for the target environment.

### 4.1 Configure kubectl

```bash
# Dev (zonal)
gcloud container clusters get-credentials dev-platform-cluster \
  --zone=us-central1-a --project=$PROJECT_ID

# Prod (regional)
gcloud container clusters get-credentials prod-platform-cluster \
  --region=us-central1 --project=$PROJECT_ID
```

Verify:
```bash
kubectl get nodes
```

### 4.2 Patch K8s manifests with real values

Several manifests contain `REPLACE_*` placeholders. Substitute them before applying. The easiest approach is a one-time sed pass from the repo root:

```bash
# Set these from the Terraform outputs
export TF_REGION=us-central1
export TF_PROJECT=$PROJECT_ID
export TF_ENV=dev   # or prod

find infra/k8s -type f -name "*.yaml" | xargs sed -i \
  -e "s/REPLACE_REGION/${TF_REGION}/g" \
  -e "s/REPLACE_PROJECT/${TF_PROJECT}/g" \
  -e "s/REPLACE_ENV/${TF_ENV}/g" \
  -e "s/REPLACE_WITH_PROJECT_ID/${TF_PROJECT}/g"
```

For the Ingress, also set your domain:
```bash
export DOMAIN=platform.example.com
sed -i "s/REPLACE_WITH_YOUR_DOMAIN/${DOMAIN}/g" infra/k8s/ingress/ingress.yaml
sed -i "s/REPLACE_ENV-ingress-ip/${TF_ENV}-ingress-ip/g" infra/k8s/ingress/ingress.yaml
```

### 4.3 Apply base layer

```bash
kubectl apply -f infra/k8s/base/namespace.yaml
kubectl apply -f infra/k8s/base/rbac.yaml
```

### 4.4 Install Strimzi operator and deploy Kafka

Install the Strimzi Operator into its own namespace:

```bash
helm repo add strimzi https://strimzi.io/charts/
helm repo update

helm install strimzi-operator strimzi/strimzi-kafka-operator \
  -n kafka --create-namespace \
  -f infra/k8s/kafka/strimzi-values.yaml
```

Wait for the operator to be ready:
```bash
kubectl wait --for=condition=available deployment/strimzi-cluster-operator \
  -n kafka --timeout=120s
```

Deploy the Kafka cluster and topics:
```bash
kubectl apply -f infra/k8s/kafka/kafka-cluster.yaml
kubectl apply -f infra/k8s/kafka/kafka-topics.yaml
```

Wait for Kafka to be ready (takes 2–3 minutes on first start):
```bash
kubectl wait kafka/platform-kafka --for=condition=Ready \
  -n kafka --timeout=300s
```

> **Prod:** The `kafka-cluster.yaml` uses `replicas: 1` (dev default). For prod, patch it to 3 replicas and set `offsets.topic.replication.factor: 3`, `min.insync.replicas: 2` before applying.

### 4.5 Push Docker images

Before deploying application services, images must exist in Artifact Registry. Authenticate Docker and push:

```bash
REPO=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw repository_url)

gcloud auth configure-docker ${TF_REGION}-docker.pkg.dev

for SERVICE in event-ingestion inference-api privacy feature-pipeline model-training; do
  docker build -t ${REPO}/${SERVICE}:latest services/${SERVICE}/
  docker push ${REPO}/${SERVICE}:latest
done
```

### 4.6 Create Kubernetes secrets

These are never committed to git. Substitute real values from the Terraform outputs.

```bash
CLOUD_SQL_IP=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw cloud_sql_private_ip)
REDIS_HOST=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw redis_host)
PRIVACY_DB_URL=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw privacy_db_url)
MLFLOW_DB_URL=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw mlflow_db_url)
PARQUET_BUCKET=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw parquet_bucket)
MLFLOW_BUCKET=$(terraform -chdir=infra/terraform/environments/${TF_ENV} output -raw mlflow_artifacts_bucket)

NS=ai-personalization-platform

# Shared secrets consumed by most services
kubectl create secret generic platform-secrets -n $NS \
  --from-literal=PSEUDONYMIZE_SECRET=$(openssl rand -hex 32) \
  --from-literal=REDIS_HOST=${REDIS_HOST} \
  --from-literal=REDIS_PORT=6379 \
  --from-literal=KAFKA_BOOTSTRAP_SERVERS=platform-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092 \
  --from-literal=INFERENCE_MLFLOW_MODEL_NAME=personalization-click-model

# Privacy service secrets (DATABASE_URL + pseudonymize secret)
kubectl create secret generic privacy-secret -n $NS \
  --from-literal=DATABASE_URL="${PRIVACY_DB_URL}" \
  --from-literal=PSEUDONYMIZE_SECRET=$(kubectl get secret platform-secrets -n $NS \
    -o jsonpath='{.data.PSEUDONYMIZE_SECRET}' | base64 -d)

# MLflow backend and artifact root
kubectl create secret generic mlflow-db-secret -n $NS \
  --from-literal=MLFLOW_BACKEND_STORE_URI="${MLFLOW_DB_URL}" \
  --from-literal=MLFLOW_ARTIFACT_ROOT="gs://${MLFLOW_BUCKET}/"
```

> **PSEUDONYMIZE_SECRET** must be the same value in both `platform-secrets` and `privacy-secret`. The snippet above reads it back from the already-created secret to avoid generating two different values.

### 4.7 Deploy application services

Deploy in this order so dependencies are satisfied before dependents start.

```bash
NS=ai-personalization-platform

# MLflow (required by inference-api and model-training)
kubectl apply -f infra/k8s/mlflow/

# Privacy (has initContainer that runs alembic — wait for it to complete)
kubectl apply -f infra/k8s/services/privacy/
kubectl rollout status deployment/privacy -n $NS

# Event ingestion and inference API
kubectl apply -f infra/k8s/services/event-ingestion/
kubectl apply -f infra/k8s/services/inference-api/
```

### 4.8 Install Flink operator and deploy feature pipeline

```bash
helm repo add flink-operator-repo \
  https://downloads.apache.org/flink/flink-kubernetes-operator-1.10.0/
helm repo update

helm install flink-kubernetes-operator \
  flink-operator-repo/flink-kubernetes-operator \
  -n $NS

kubectl apply -f infra/k8s/services/feature-pipeline/flink-deployment.yaml
```

### 4.9 Deploy model-training CronJob

```bash
kubectl apply -f infra/k8s/model-training/cronjob.yaml
```

The job runs at 2am UTC daily. To trigger it manually for a smoke test:
```bash
kubectl create job --from=cronjob/model-training model-training-manual-$(date +%s) \
  -n $NS
```

### 4.10 Apply Ingress

```bash
kubectl apply -f infra/k8s/ingress/ingress.yaml
```

The GKE Ingress provisions a Cloud Load Balancer and requests a Google-managed TLS certificate. Certificate provisioning takes 10–60 minutes; the domain must have an A record pointing to the static IP reserved by Terraform.

Get the static IP:
```bash
gcloud compute addresses describe ${TF_ENV}-ingress-ip \
  --global --project=$PROJECT_ID --format='value(address)'
```

### 4.11 Verify the deployment

```bash
# All pods should be Running or Completed
kubectl get pods -n ai-personalization-platform
kubectl get pods -n kafka

# Kafka cluster should be Ready
kubectl get kafka -n kafka

# Flink deployment should be Running
kubectl get flinkdeployment -n ai-personalization-platform

# HPA should show current/desired replica counts
kubectl get hpa -n ai-personalization-platform

# Check Ingress has an address
kubectl get ingress -n ai-personalization-platform
```

---

## Part 5 — Prod-specific differences

| Concern | Dev | Prod |
|---|---|---|
| GKE location | Zonal (`us-central1-a`) | Regional (`us-central1`) — HA across 3 zones |
| GKE cluster management fee | Free | $73/month |
| Cloud SQL tier | `db-f1-micro` | `db-g1-small` |
| Cloud SQL deletion protection | Off | On — must be disabled manually before `terraform destroy` |
| GKE deletion protection | Off | On |
| Memorystore tier | BASIC | STANDARD_HA (replication) |
| Kafka replicas | 1 (combined KRaft node) | 3 (patch `kafka-cluster.yaml`) |
| Kafka replication factor | 1 | 3 (patch `kafka-cluster.yaml`) |
| apps-spot machine type | `e2-standard-2` | `e2-standard-4` |
| apps-spot min/max nodes | 2 / 5 | 3 / 8 |

### Kafka prod patch

Before applying `kafka-cluster.yaml` in prod, update the replicas and replication factors:

```bash
# In kafka-cluster.yaml
# KafkaNodePool: replicas: 3
# Kafka config:
#   offsets.topic.replication.factor: 3
#   transaction.state.log.replication.factor: 3
#   transaction.state.log.min.isr: 2
#   default.replication.factor: 3
#   min.insync.replicas: 2
```

### Disabling prod deletion protection (before destroy)

```bash
# Cloud SQL
gcloud sql instances patch prod-platform-pg \
  --no-deletion-protection --project=$PROJECT_ID

# GKE cluster — edit Terraform and apply, or patch via gcloud
gcloud container clusters update prod-platform-cluster \
  --no-enable-deletion-protection \
  --region=us-central1 --project=$PROJECT_ID
```

---

## Teardown

### Dev

```bash
kubectl delete -f infra/k8s/ --recursive
helm uninstall strimzi-operator -n kafka
helm uninstall flink-kubernetes-operator -n ai-personalization-platform

cd infra/terraform/environments/dev
terraform destroy
```

### Prod

Disable deletion protection first (see above), then:

```bash
cd infra/terraform/environments/prod
terraform destroy
```

> The GCS parquet and MLflow artifact buckets have `force_destroy = false` in prod. Delete their contents manually before `terraform destroy` or set `force_destroy = true` in `infra/terraform/modules/gcs/main.tf` temporarily.

---

## Secrets reference

| Secret name | Namespace | Keys | Consumed by |
|---|---|---|---|
| `platform-secrets` | `ai-personalization-platform` | `PSEUDONYMIZE_SECRET`, `REDIS_HOST`, `REDIS_PORT`, `KAFKA_BOOTSTRAP_SERVERS`, `INFERENCE_MLFLOW_MODEL_NAME` | event-ingestion, inference-api, feature-pipeline, model-training |
| `privacy-secret` | `ai-personalization-platform` | `DATABASE_URL`, `PSEUDONYMIZE_SECRET` | privacy (main container + alembic initContainer) |
| `mlflow-db-secret` | `ai-personalization-platform` | `MLFLOW_BACKEND_STORE_URI`, `MLFLOW_ARTIFACT_ROOT` | mlflow |
