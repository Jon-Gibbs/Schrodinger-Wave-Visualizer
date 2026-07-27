# Containerized Schrödinger Wave Equation Engine

A cloud-native physics simulation that modernizes a legacy Fortran codebase into a fully parallelized, observable, and visualized system on AWS. The application computes a 2D locus of the Schrödinger Wave Equation across a distributed Kubernetes cluster and streams results to a real-time 3D animation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Amazon EKS Cluster                   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Worker Pod 0│  │  Worker Pod 1│  │  Worker Pod N│      │
│  │  (index 0)   │  │  (index 1)   │  │  (index 9)   │      │
│  │  Fortran →   │  │  Fortran →   │  │  Fortran →   │      │
│  │  JSON chunk  │  │  JSON chunk  │  │  JSON chunk  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                  │              │
│  ┌──────────────────────────────────────┐    │              │
│  │  Prometheus + Grafana (Observability)│    │              │
│  └──────────────────────────────────────┘    │              │
└─────────────────────────────────────────────┼──────────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  Amazon EC2 (Redis) │
                                    │  Pub/Sub Broker     │
                                    └─────────┬──────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  Local Visualizer   │
                                    │  (Matplotlib 3D)    │
                                    └────────────────────┘
```

## Project Structure

```
containerized-schrodinger-application/
├── src/
│   ├── Dockerfile              # Multi-stage build (gfortran builder → slim runtime)
│   ├── parallel_worker.py      # Kubernetes pod entrypoint; computes & publishes results
│   ├── requirements.txt        # Worker dependencies (numpy, redis)
│   └── app/fortran/
│       └── schrodinger.f90     # Legacy Fortran implementation of the wave equation
├── visualizer/
│   ├── visualizer.py           # Local client; subscribes to Redis & renders 3D animation
│   └── requirements.txt        # Visualizer dependencies (matplotlib, redis, sshtunnel)
├── kubernetes/
│   ├── indexed-job.yaml        # Kubernetes IndexedJob (10 completions, parallelism 5)
│   ├── prometheus-config.yaml  # Prometheus ConfigMap with scrape configuration
│   ├── prometheus.yaml         # Prometheus deployment, RBAC, and service
│   ├── grafana.yaml            # Grafana deployment with pre-built dashboards
│   └── DELIVERABLE-4-README.md # Observability stack deployment guide
└── docker-commands.txt         # Build, tag, and push reference commands
```

## Prerequisites

| Tool | Purpose |
|------|---------|
| Docker (with `buildx`) | Build multi-platform images |
| AWS CLI | ECR authentication, EKS cluster management |
| `kubectl` | Deploy and manage Kubernetes resources |
| `eksctl` | Provision the EKS cluster and node group |
| Python 3.11+ | Run the local visualizer |
| SSH key pair | Tunnel into the EC2 Redis instance |

## Deliverable 1 — Docker Image

The Dockerfile uses a two-stage build to keep the runtime image lean:

- **Builder stage**: installs `gfortran`, `gcc`, and `f2py` to compile `schrodinger.f90` into a Python extension module (`schrodinger*.so`).
- **Runtime stage**: copies only the compiled `.so` and `parallel_worker.py` into a `python:3.11-slim` image.

### Build and push to ECR

> EKS nodes are ARM64. Always target `linux/arm64`.

```bash
# Build for ARM64
docker buildx build --platform linux/arm64 -t fortran-kubernetes:latest --load src/

# Tag for ECR
docker tag fortran-kubernetes:latest \
  <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/fortran-kubernetes:latest

# Authenticate and push
aws ecr get-login-password --region <REGION> | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com

docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/fortran-kubernetes:latest
```

## Deliverable 2 — EKS Cluster & Kubernetes IndexedJob

Provision a cluster with at least 3 nodes, then submit the indexed job:

```bash
# Deploy the job
kubectl apply -f kubernetes/indexed-job.yaml

# Monitor progress
kubectl get jobs
kubectl get pods -l app=schrodinger-worker
kubectl logs <pod-name>
```

The job runs **10 pods** (indices 0–9) with a **parallelism of 5**. Each pod reads its `JOB_COMPLETION_INDEX` environment variable, computes its assigned matrix chunk using the Fortran module, and publishes the result to Redis.

## Deliverable 3 — Redis Broker on EC2

Each worker pod serializes its computed 64×64 amplitude matrix to JSON and:
1. **Publishes** the payload to the `schrodinger-results` Redis channel (real-time).
2. **Persists** the payload to the `schrodinger-results-list` Redis list (durable).

Configure worker pods via environment variables in `indexed-job.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | EC2 private or public IP |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | *(none)* | Redis auth password |
| `REDIS_CHANNEL` | `schrodinger-results` | Pub/Sub channel name |
| `GRID_SIZE` | `64` | Wave matrix dimension |
| `H_BAR` | `1.0` | Reduced Planck constant |
| `MASS` | `1.0` | Particle mass |

## Deliverable 4 — Prometheus & Grafana Observability

Deploy the full observability stack using the manifests in `kubernetes/`:

```bash
kubectl apply -f kubernetes/prometheus-config.yaml
kubectl apply -f kubernetes/prometheus.yaml
kubectl rollout status deployment/prometheus

kubectl apply -f kubernetes/grafana.yaml
kubectl rollout status deployment/grafana
```

Access Grafana on port `30000` of any EKS node's public IP:

```
http://<NODE-PUBLIC-IP>:30000
```

Default credentials: `admin` / `admin`

Prometheus scrapes kubelet metrics from all nodes via Kubernetes service discovery and retains 24 hours of time-series data. Grafana dashboards display active CPU load and job execution metrics.

See [kubernetes/DELIVERABLE-4-README.md](kubernetes/DELIVERABLE-4-README.md) for full deployment details.

## Deliverable 5 — Real-Time Visualizer

The local visualizer subscribes to Redis and assembles incoming matrix chunks into a live 3D surface plot.

### Install dependencies

```bash
cd visualizer
pip install -r requirements.txt
```

### Run (direct connection)

```bash
python visualizer.py --redis-host <EC2-PUBLIC-IP> --redis-port 6379
```

### Run (via SSH tunnel)

```bash
python visualizer.py \
  --redis-host <EC2-PRIVATE-IP> \
  --redis-port 6379 \
  --ssh-host <EC2-PUBLIC-IP> \
  --ssh-key ~/.ssh/<your-key>.pem \
  --ssh-username ubuntu
```

The visualizer waits for all 10 pod results (indices 0–9), then renders a 3D surface plot of the assembled wave function using Matplotlib.

## Redeploy After Image Update

```bash
kubectl delete job schrodinger-indexed-job
kubectl apply -f kubernetes/indexed-job.yaml
```

## Technology Stack

- **Fortran / f2py** — Legacy physics engine compiled as a Python extension
- **Docker / Amazon ECR** — Multi-stage container build and registry
- **Amazon EKS** — Managed Kubernetes for parallel batch execution
- **Amazon EC2 + Redis** — Pub/Sub broker and persistent result store
- **Prometheus + Grafana** — Cluster metrics collection and dashboards
- **Python + Matplotlib** — Real-time 3D wave function visualization
