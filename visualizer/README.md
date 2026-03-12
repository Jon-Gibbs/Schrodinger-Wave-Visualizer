# Schrödinger Wave Visualizer

Local Python application that subscribes to Redis, collects wave computation results from Kubernetes pods, and displays a 3D surface visualization of the Schrödinger wave function.

## Overview

**Option A (Implemented)**: Wait for all 10 pod results to arrive, then display a static 3D Matplotlib surface plot.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Local Machine (visualizer.py)                              │
│                                                               │
│  ┌─────────────────┐                                         │
│  │ RedisSubscriber │─────────────┐                           │
│  │                 │             │                           │
│  │ Connect → Redis │             │                           │
│  │ Receive JSON    │             │ Messages                  │
│  └─────────────────┘             │ (amplitude matrices)      │
│                                   ↓                           │
│                          ┌──────────────────┐                │
│                          │  DataBuffer      │                │
│                          │                  │                │
│                          │ Store by job_idx │                │
│                          │ Track completion │                │
│                          │ Assemble matrix  │                │
│                          └──────────────────┘                │
│                                   │                           │
│                                   ↓ (when all 10 received)   │
│                          ┌──────────────────┐                │
│                          │ WaveVisualizer   │                │
│                          │                  │                │
│                          │ Plot 3D surface  │                │
│                          │ Show Matplotlib  │                │
│                          └──────────────────┘                │
│                                   │                           │
│                                   ↓                           │
│                          [User sees 3D plot]                 │
└──────────────────────────────────────────────────────────────┘
                                   ↑
                                   │ JSON messages with
                                   │ full 64x64 amplitude
                    ┌──────────────┴─────────────────────┐
                    │                                    │
            ┌───────────────────────┐        ┌──────────────────┐
            │ AWS EC2: Redis Server │        │ AWS EKS Cluster  │
            │ 172.31.31.172:6379    │←───────│ 10 Pods (0-9)    │
            │                       │ Pub/Sub │ Publishing to    │
            │ Channel:              │         │ "schrodinger-    │
            │ "schrodinger-results" │         │  results"        │
            └───────────────────────┘        └──────────────────┘
```

## Data Flow

1. **Kubernetes pods** (parallel_worker.py):
   - Compute Schrödinger wave matrix independently
   - Publish JSON with full 64×64 amplitude matrix
   - Message: `{"job_completion_index": 0-9, "amplitude": [...], "min": ..., "max": ..., "mean": ...}`

2. **Local visualizer**:
   - Subscribes to `schrodinger-results` channel
   - Receives 10 JSON messages (possibly out of order)
   - Buffers each by pod index
   - When all 10 received: assembles into 640×64 matrix
   - Plots 3D surface using Matplotlib with viridis colormap
   - Displays global min/max/mean statistics

## Installation

```bash
cd visualizer
pip install -r requirements.txt
```

## Usage

### Basic (Default Redis: 172.31.31.172:6379)

```bash
python visualizer.py
```

### With Custom Redis Host/Port

```bash
python visualizer.py --redis-host 172.31.31.172 --redis-port 6379
```

### With Password Authentication

```bash
python visualizer.py --redis-password your_password
```

### Custom Timeout (default: 120 seconds)

```bash
python visualizer.py --timeout 60
```

### Save Plot to File

```bash
python visualizer.py --save-plot wave_plot.png
```

## Output

The visualizer logs every step:

```
========================================================================
SCHRÖDINGER WAVE VISUALIZER - Starting
========================================================================
2024-01-15 14:23:45,123 - __main__ - INFO - Initialized Redis subscriber: 172.31.31.172:6379
2024-01-15 14:23:45,456 - __main__ - INFO - Connecting to Redis at 172.31.31.172:6379...
2024-01-15 14:23:45,500 - __main__ - INFO - ✓ Successfully connected to Redis
2024-01-15 14:23:45,501 - __main__ - INFO - Subscribing to channel 'schrodinger-results'...
2024-01-15 14:23:45,502 - __main__ - INFO - ✓ Subscribed to 'schrodinger-results'
2024-01-15 14:23:45,503 - __main__ - INFO - Listening for messages...
2024-01-15 14:23:50,123 - __main__ - INFO - ✓ Received result 1/10 (pod index 3)
2024-01-15 14:23:50,124 - __main__ - INFO - Status: [_ _ _ X _ _ _ _ _ _] (1/10)
...
2024-01-15 14:23:65,789 - __main__ - INFO - ✓ ALL RESULTS RECEIVED!
========================================================================
ASSEMBLING MATRIX
========================================================================
2024-01-15 14:23:65,900 - __main__ - INFO - ✓ Assembled matrix shape: (640, 64)
========================================================================
PLOTTING WAVE FUNCTION
========================================================================
2024-01-15 14:23:66,100 - __main__ - INFO - Creating 3D surface plot...
2024-01-15 14:23:67,500 - __main__ - INFO - Plotting surface...
2024-01-15 14:23:68,200 - __main__ - INFO - ✓ Successfully plotted surface
2024-01-15 14:23:68,201 - __main__ - INFO - Close the plot window to exit
```

## Key Classes

### `RedisSubscriber`

Manages connection to Redis server and subscribes to pub/sub channel.

- `connect()`: Establish TCP connection, verify with PING
- `subscribe(channel)`: Join channel
- `listen()`: Generator yielding JSON message strings

### `DataBuffer`

Buffers incoming messages and tracks completion status.

- `add_result(json_message)`: Parse JSON and store by pod index
- `is_complete()`: Check if all 10 pods reported
- `get_assembled_matrix()`: Stack chunks into final 640×64 matrix
- `print_status()`: Show which pods have reported

### `WaveVisualizer`

Creates and displays 3D Matplotlib plot.

- `plot_matrix(matrix)`: Create surface plot from numpy array
- `show()`: Display plot (blocking call)
- `save(filename)`: Export to PNG/PDF

## Matrix Assembly

Each of the 10 pods computes a 64×64 amplitude matrix. The visualizer:

1. **Receives** 10 JSON messages with full matrices (possibly out of order)
2. **Buffers** by pod index (0-9)
3. **Assembles** by vertical stacking → 640×64 matrix
4. **Averages** across the 10 chunks to get a 64×64 representation
5. **Plots** the 64×64 averaged matrix as a 3D surface

This allows visualization of how different job indices contributed to the overall wave.

## Expected Runtime

- Redis connection: ~100ms
- Waiting for 10 pods (job runs ~20s): ~25s total
- Matrix assembly: ~1s
- Plot generation: ~2s
- **Total**: ~30 seconds from visualizer start to plot display

## Troubleshooting

### "Connection refused"

- Verify Redis is running: `redis-cli ping` on Redis EC2
- Check security group allows TCP 6379 from your IP
- Verify pod is publishing: `redis-cli SUBSCRIBE schrodinger-results`

### "Timeout after 120s"

- Pods may still be running. Check: `kubectl get pods`
- Increase timeout: `--timeout 300`
- Check pod logs: `kubectl logs <pod-name>`

### "No message received"

- Verify job is running: `kubectl get jobs`
- Check if pods are publishing: `redis-cli XLEN schrodinger-results`
- Verify JSON format in pod logs

### Plot looks strange (very jagged/noisy)

- This is expected for random/stochastic data
- Try reducing grid size (GRID_SIZE env var in job) for smoother visualization
- Check that amplitude values are reasonable (not NaN or Inf)

## Future Enhancements

- **Option B (Not Implemented)**: Animate as results arrive (real-time streaming)
- **Option C (Not Implemented)**: Interactive 3D plot with rotation/zoom
- Heatmap contour lines overlaying surface
- Export to animation (MP4) instead of static plot
- Compare matrices from different job completions

## Related Files

- `../src/parallel_worker.py`: Publishes results to Redis
- `../kubernetes/indexed-job.yaml`: Defines Kubernetes Job
- `../src/Dockerfile`: Container image with Fortran + Python

