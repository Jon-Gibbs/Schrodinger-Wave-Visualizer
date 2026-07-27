
Final Lab Assignment
You have been contracted by a research lab to modernize their monolithic physics engine. Their core math calculates a 2D locus of the Schrödinger Wave Equation using legacy Fortran.

Currently, this runs sequentially on a single bare-metal server. It is slow, unobservable, and non-scalable.

our Mandate
Containerize the Fortran math logic.
Parallelize the workload using Kubernetes Batch Jobs on Amazon EKS.
Broker the partial results via an EC2 Redis Server.
Observe cluster metrics using Prometheus & Grafana.
Visualize the real-time wave using Python Matplotlib.

Deliverable 1:
You must compile the legacy schrodinger.f90 file into a Python module and package it into an optimized, multi-stage Docker image.

Requirements:
Use f2py (NumPy) to compile the Fortran code.
Write a Python wrapper script (parallel_worker.py) that accepts a JOB_COMPLETION_INDEX environment variable.
Implement a Multi-Stage Dockerfile separating the build tools (gfortran) from the runtime.
Push the image to Amazon Elastic Container Registry (ECR).

Deliverable 2:
Provision an AWS EKS Cluster and orchestrate the workload to compute massive matrices in parallel.

Requirements:
Deploy a NodeGroup with at least 3 compute instances.
Write and apply a Kubernetes Indexed Job YAML manifest configuring at least 10 completions and a parallelism factor of 5.

Deliverable 3:
The EKS worker pods must stream their computed matrix chunks to a central broker so a client can assemble the final 3D wave.

Requirements:
Provision a public-facing Amazon EC2 instance.
Install, configure, and secure a Redis Server on the EC2 instance to act as a Pub/Sub broker and persistent storage of logs.
Update the parallel_worker.py in your Docker container to serialize the matrix chunks to JSON and publish them to a Redis channel (e.g., wave_channel).
Mak

Deliverable 4:
You cannot optimize what you cannot measure. Deploy the industry-standard observability stack to your EKS cluster.

Requirements:
Implement the Sidecar Pattern: Deploy a metrics exporter container alongside your main workloads.
Configure a Prometheus ConfigMap using Kubernetes Service Discovery to automatically scrape the sidecars.
Deploy Grafana, expose it via a NodePort, and construct a dashboard showing active CPU load and job execution metrics.

Deliverable 5:
Complete the architecture by building the client application and documenting your system's performance.

Requirements:
Write a local Python application using Matplotlib that subscribes to your EC2 Redis server.
Animate the incoming JSON payloads into a dynamic 3D surface plot.
The Deliverable: Record a tiled video (.mp4 or .mov) showing the Matplotlib animation running side-by-side with the live Grafana CPU Dashboard.