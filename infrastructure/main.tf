provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. GKE Cluster (Private Cluster)
resource "google_container_cluster" "primary" {
  name     = "cloud-bp-advisor-gke"
  location = var.region
  
  # GKE Cluster Base Configuration
  deletion_protection      = false
  initial_node_count       = 1
  remove_default_node_pool = true
  
  # 프라이빗 클러스터 설정 (외부에서 Node IP 접근 차단 등)
  # private_cluster_config {
  #   enable_private_nodes    = true
  #   enable_private_endpoint = false
  #   master_ipv4_cidr_block  = "172.16.0.0/28"
  # }
}

# Sandbox Worker 전용 격리 Node Pool 
resource "google_container_node_pool" "sandbox_pool" {
  name       = "sandbox-node-pool"
  cluster    = google_container_cluster.primary.name
  location   = var.region
  node_count = 1 # gVisor 샌드박스 실행용

  node_config {
    machine_type = "e2-standard-4"
    sandbox_config {
      type = "GVISOR"
    }
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

# 2. Main Backend UI - Cloud Run
resource "google_cloud_run_v2_service" "agent_backend" {
  name     = "agent-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/cba-repo/agent-backend:latest"
      ports {
        container_port = 8000
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.agent_backend.location
  project  = google_cloud_run_v2_service.agent_backend.project
  name     = google_cloud_run_v2_service.agent_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 3. Async Messaging - GCP Pub/Sub
resource "google_pubsub_topic" "job_topic" {
  name = "sandbox-job-topic"
}

resource "google_pubsub_subscription" "job_sub" {
  name  = "sandbox-job-sub-v2"
  topic = google_pubsub_topic.job_topic.name
  message_retention_duration = "86400s" # 1일 보관
}

# 3. Artifact Storage - GCS
resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_id}-cba-artifacts"
  location      = var.region
  force_destroy = true
  uniform_bucket_level_access = true
}

# 4. State & Logging - Firestore Database
resource "google_firestore_database" "cloud_bp_db" {
  project     = var.project_id
  name        = "cloud-bp-db"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  deletion_policy = "DELETE"
}

# Optional: Manage other databases if they are part of the project scope
# 5. Artifact Registry - Container Images
resource "google_artifact_registry_repository" "cba_repo" {
  location      = var.region
  repository_id = "cba-repo"
  description   = "Docker repository for Cloud BP Advisor"
  format        = "DOCKER"
}
