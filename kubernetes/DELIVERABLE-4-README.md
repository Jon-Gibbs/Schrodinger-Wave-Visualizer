# Deliverable 4: Prometheus + Grafana Monitoring

This directory contains the Kubernetes manifests for deploying Prometheus (metrics collection) and Grafana (metrics visualization) to monitor the Schrödinger Wave Equation job execution.

## Files

- **prometheus-config.yaml** - ConfigMap with Prometheus scrape configuration
- **prometheus.yaml** - Prometheus deployment with RBAC, service, and storage
- **grafana.yaml** - Grafana deployment with pre-built dashboards and data source

## Deployment Steps

### 1. Apply ConfigMaps and Prometheus

```bash
kubectl apply -f kubernetes/prometheus-config.yaml
kubectl apply -f kubernetes/prometheus.yaml
```

**Wait for Prometheus to be ready:**
```bash
kubectl rollout status deployment/prometheus
```

### 2. Apply Grafana

```bash
kubectl apply -f kubernetes/grafana.yaml
```

**Wait for Grafana to be ready:**
```bash
kubectl rollout status deployment/grafana
```

### 3. Verify Everything is Running

```bash
kubectl get pods
kubectl get services

# Should see:
# prometheus-xxxxx          1/1 Running
# grafana-xxxxx             1/1 Running
# grafana-service           NodePort   10.x.x.x  <none>  3000:30000/TCP
# prometheus-service        ClusterIP  10.x.x.x  <none>  9090/TCP
```

### 4. Access Grafana Dashboard

Get your EC2 node's public IP:
```bash
aws ec2 describe-instances --filters "Name=instance.group-name,Values=launch-wizard-4" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text
```

Open in browser:
```
http://<EC2-PUBLIC-IP>:30000
```

**Default credentials:**
- Username: `admin`
- Password: `admin`

(Or just click through anonymous access)

## Architecture

```
Kubernetes Cluster
├── worker-pod-0 (parallel_worker.py)
│   └── Exposes CPU/memory metrics
├── worker-pod-1
│   └── Exposes CPU/memory metrics
├── ... (8 more pods)
│
├── prometheus-pod
│   ├── Scrapes kubelet from all nodes
│   ├── Discovers pods and metrics
│   └── Stores time-series data (24 hours)
│
└── grafana-pod
    ├── Queries Prometheus
    ├── Displays dashboards
    └── Accessible on :30000 (NodePort)
```

## How It Works

### Prometheus

1. **Service Discovery**: Queries Kubernetes API for nodes, pods, services
2. **Scraping**: Periodically fetches metrics from kubelet (port 10250)
3. **Storage**: Stores metrics in time-series database
4. **Retention**: Keeps 24 hours of data by default

### Metrics Collected

- **Node metrics**: CPU, memory, disk, network per node
- **Pod metrics**: CPU, memory per pod (via kubelet)
- **Kubernetes metrics**: Pod status, job completion

### Grafana Dashboard

Pre-built dashboard shows:
- **CPU Usage**: Per-pod CPU consumption during job execution
- **Memory Usage**: Per-pod memory during computation
- **Running Pods**: Count of currently running pods (increases as job scales)
- **Completed Pods**: Count of finished pods (increases as job completes)

## Querying Metrics

Direct Prometheus queries (for debugging):

```bash
# SSH tunnel to Prometheus (in separate terminal)
ssh -i ~/.ssh/macbook_pro.pem -L 9090:localhost:9090 ubuntu@54.201.238.130

# Access Prometheus UI
# http://localhost:9090/graph
```

Example PromQL queries:
```
# CPU usage of all pods
sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)

# Memory usage of all pods
sum(container_memory_usage_bytes) by (pod)

# Number of running pods
count(kube_pod_status_phase{phase="Running"})

# Job completion rate
rate(kube_job_status_succeeded[1m])
```

## RBAC Permissions

Prometheus runs with a ServiceAccount that has ClusterRole access to:
- `nodes` and `nodes/proxy` (for kubelet metrics)
- `pods` (pod discovery)
- `services` (service discovery)
- `endpoints` (endpoint discovery)
- `configmaps` (configuration)
- `metrics.k8s.io` (metrics API)

This allows Prometheus to discover and monitor all resources in the cluster.

## Running the Full Pipeline

1. **Deploy Prometheus + Grafana** (this Deliverable 4)
2. **Deploy Indexed Job**:
   ```bash
   kubectl apply -f kubernetes/indexed-job.yaml
   ```
3. **Watch in Grafana**:
   - Open browser to `http://<EC2-IP>:30000`
   - Watch CPU/memory spike as pods start
   - Watch "Running Pods" counter increase
   - Watch "Completed Pods" counter increase as job finishes

4. **Run Visualizer** (Deliverable 5):
   ```bash
   python visualizer/visualizer.py
   ```
   (Or use SSH tunnel to Redis and run visualizer)

## Troubleshooting

### Prometheus can't scrape metrics
```bash
# Check Prometheus logs
kubectl logs deployment/prometheus

# Verify service account permissions
kubectl describe sa prometheus
kubectl describe clusterrole prometheus
```

### Grafana shows no data
```bash
# Check Grafana logs
kubectl logs deployment/grafana

# Verify Prometheus is running and scraping
kubectl port-forward svc/prometheus-service 9090:9090
# Visit http://localhost:9090/targets (should show all endpoints healthy)

# Verify data source configuration in Grafana
# Settings → Data Sources → Prometheus
# should point to: http://prometheus-service:9090
```

### Dashboards not loading
```bash
# Check ConfigMaps
kubectl get configmaps
kubectl describe cm grafana-dashboards

# Restart Grafana pod
kubectl rollout restart deployment/grafana
```

## Cleanup

Remove all monitoring resources:
```bash
kubectl delete -f kubernetes/grafana.yaml
kubectl delete -f kubernetes/prometheus.yaml
kubectl delete configmap prometheus-config
```

## Next Steps

- Add custom metrics from `parallel_worker.py` (computation time, wave statistics)
- Create alert rules (notify if pods use >80% CPU)
- Export metrics to external monitoring system
- Store metrics on persistent volume for long-term analysis
