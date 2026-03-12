#!/usr/bin/env python3
"""
Schrödinger Wave Equation Visualizer - Deliverable 5

This application:
1. Subscribes to Redis pub/sub channel "schrodinger-results"
2. Waits for all 10 pod results to arrive (from job indices 0-9)
3. Assembles the 64x64 amplitude matrix from received chunks
4. Displays a 3D surface plot of the wave function

Option A (Simple): Wait for all 10 results, then draw static 3D plot

Usage:
    python visualizer.py --redis-host 172.31.31.172 --redis-port 6379
"""

import json
import logging
import argparse
import numpy as np
import redis
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
import time
from typing import Dict, Optional
from sshtunnel import SSHTunnelForwarder


# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# REDIS SUBSCRIBER CLASS
# ============================================================================

class RedisSubscriber:
    """
    Manages Redis pub/sub subscription to receive Schrödinger results.
    
    This class:
    - Connects to Redis server
    - Subscribes to "schrodinger-results" channel
    - Listens for incoming JSON messages from pods
    """
    
    def __init__(self, host: str = "localhost", port: int = 6379, 
                 password: Optional[str] = None, 
                 ssh_host: Optional[str] = None, ssh_key: Optional[str] = None,
                 ssh_username: str = "ubuntu"):
        """
        Initialize Redis connection.
        
        Args:
            host: Redis server hostname/IP
            port: Redis server port
            password: Optional Redis password (for auth)
            ssh_host: Optional SSH host (EC2 instance) for tunneling
            ssh_key: Optional path to SSH private key file
            ssh_username: SSH username (default: ubuntu)
        """
        self.host = host
        self.port = port
        self.password = password
        self.ssh_host = ssh_host
        self.ssh_key = ssh_key
        self.ssh_username = ssh_username
        self.client = None
        self.pubsub = None
        self.tunnel = None
        
        if ssh_host:
            logger.info(f"Initializing Redis subscriber via SSH tunnel: {ssh_username}@{ssh_host} -> {host}:{port}")
        else:
            logger.info(f"Initializing Redis subscriber: {host}:{port}")
    
    def connect(self) -> bool:
        """
        Establish connection to Redis server (with optional SSH tunnel).
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # If SSH tunneling is requested, establish tunnel first
            if self.ssh_host and self.ssh_key:
                logger.info(f"Establishing SSH tunnel to {self.ssh_username}@{self.ssh_host}...")
                try:
                    self.tunnel = SSHTunnelForwarder(
                        (self.ssh_host, 22),
                        ssh_username=self.ssh_username,
                        ssh_pkey=self.ssh_key,
                        remote_bind_address=(self.host, self.port),
                        logger=logger
                    )
                    self.tunnel.start()
                    logger.info(f"✓ SSH tunnel established on localhost:{self.tunnel.local_bind_port}")
                    
                    # Connect via tunnel (localhost)
                    logger.info(f"Connecting to Redis through SSH tunnel...")
                    self.client = redis.StrictRedis(
                        host='127.0.0.1',
                        port=self.tunnel.local_bind_port,
                        password=self.password,
                        decode_responses=True,
                        socket_connect_timeout=5
                    )
                except Exception as e:
                    logger.error(f"✗ SSH tunnel failed: {e}")
                    return False
            else:
                # Direct connection (no SSH tunnel)
                logger.info(f"Connecting to Redis at {self.host}:{self.port}...")
                self.client = redis.StrictRedis(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    decode_responses=True,  # Return strings, not bytes
                    socket_connect_timeout=5
                )
            
            # Test connection with PING
            response = self.client.ping()
            if response:
                logger.info("✓ Successfully connected to Redis")
                return True
        except Exception as e:
            logger.error(f"✗ Failed to connect to Redis: {e}")
            if self.tunnel:
                self.tunnel.stop()
            return False
    
    def subscribe(self, channel: str = "schrodinger-results") -> bool:
        """
        Subscribe to a Redis pub/sub channel.
        
        Args:
            channel: Channel name to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        try:
            logger.info(f"Subscribing to channel '{channel}'...")
            self.pubsub = self.client.pubsub()
            self.pubsub.subscribe(channel)
            logger.info(f"✓ Subscribed to '{channel}'")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to subscribe: {e}")
            return False
    
    def listen(self):
        """
        Generator that yields messages from subscribed channel.
        
        Yields:
            dict: Message data (if type='message', else None)
        """
        logger.info("Listening for messages...")
        try:
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    # Return the message data (JSON string)
                    yield message['data']
        except Exception as e:
            logger.error(f"✗ Error while listening: {e}")


# ============================================================================
# DATA BUFFER CLASS
# ============================================================================

class DataBuffer:
    """
    Manages incoming data from Redis.
    
    This class:
    - Stores received results indexed by job_completion_index (0-9)
    - Tracks how many pods have reported results
    - Parses JSON messages and validates format
    - Checks if all 10 results are received
    - Assembles final matrix when complete
    """
    
    def __init__(self, expected_pods: int = 10, grid_size: int = 64):
        """
        Initialize data buffer.
        
        Args:
            expected_pods: Number of pods expected (10 for this assignment)
            grid_size: Size of each wave matrix (64x64)
        """
        self.expected_pods = expected_pods
        self.grid_size = grid_size
        self.results = {}  # Key: job_index, Value: parsed JSON payload
        self.received_count = 0
        self.all_stats = {
            'min_values': [],
            'max_values': [],
            'mean_values': []
        }
        
        logger.info(f"Initialized DataBuffer: expecting {expected_pods} pods")
    
    def add_result(self, json_message: str) -> bool:
        """
        Parse JSON message and add to buffer.
        
        Args:
            json_message: JSON string from Redis
            
        Returns:
            True if successfully added, False if parsing failed
        """
        try:
            # Parse JSON
            payload = json.loads(json_message)
            job_index = payload.get('job_completion_index')
            
            if job_index is None:
                logger.warning("Message missing 'job_completion_index'")
                return False
            
            if job_index in self.results:
                logger.warning(f"Duplicate result for pod {job_index}, ignoring")
                return False
            
            # Store result
            self.results[job_index] = payload
            self.received_count += 1
            
            # Track statistics
            self.all_stats['min_values'].append(payload.get('min', 0))
            self.all_stats['max_values'].append(payload.get('max', 0))
            self.all_stats['mean_values'].append(payload.get('mean', 0))
            
            logger.info(
                f"✓ Received result {self.received_count}/{self.expected_pods} "
                f"(pod index {job_index})"
            )
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Error adding result: {e}")
            return False
    
    def is_complete(self) -> bool:
        """
        Check if all pod results have been received.
        
        Returns:
            True if all 10 results received, False otherwise
        """
        return self.received_count == self.expected_pods
    
    def print_status(self):
        """Log current buffer status."""
        status_list = [str(i) if i in self.results else "_" 
                       for i in range(self.expected_pods)]
        logger.info(f"Status: [{' '.join(status_list)}] "
                   f"({self.received_count}/{self.expected_pods})")
    
    def get_assembled_matrix(self) -> Optional[np.ndarray]:
        """
        Assemble complete 64x64 matrix from all 10 pod results.
        
        This is a simple concatenation approach:
        - Stack the 10 chunks (each 64x64) into a larger structure
        - OR overlay them onto a single 64x64 matrix
        
        For now, we'll create a 640x64 matrix (vertical stack of 10 chunks).
        The actual assembly depends on how the Fortran code splits the work.
        
        Returns:
            numpy array of assembled matrix, or None if not complete
        """
        if not self.is_complete():
            logger.error("Cannot assemble matrix: not all results received")
            return None
        
        try:
            # Simple approach: vertically stack the 10 chunks
            # This creates a 640x64 matrix (10 pods × 64x64)
            chunks = []
            for i in range(self.expected_pods):
                amplitude = np.array(self.results[i]['amplitude'])
                chunks.append(amplitude)
            
            # Stack all chunks vertically
            assembled = np.vstack(chunks)
            logger.info(f"✓ Assembled matrix shape: {assembled.shape}")
            
            return assembled
            
        except Exception as e:
            logger.error(f"Error assembling matrix: {e}")
            return None


# ============================================================================
# WAVE VISUALIZER CLASS
# ============================================================================

class WaveVisualizer:
    """
    Displays Schrödinger wave as a 3D surface plot.
    
    This class:
    - Creates a 3D matplotlib figure
    - Plots the amplitude matrix as a surface
    - Applies colormapping and labels
    - Shows statistics overlaid on plot
    """
    
    def __init__(self, title: str = "Schrödinger Wave Function"):
        """
        Initialize visualizer.
        
        Args:
            title: Title for the figure
        """
        self.title = title
        self.fig = None
        self.ax = None
        
        logger.info(f"Initialized WaveVisualizer: {title}")
    
    def plot_matrix(self, matrix: np.ndarray, 
                   stats: Dict = None) -> bool:
        """
        Create and display 3D surface plot of amplitude matrix.
        
        Args:
            matrix: 2D or 3D numpy array to visualize
            stats: Optional dict with 'min_values', 'max_values', 'mean_values'
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Creating 3D surface plot...")
            
            # Create figure and 3D axis
            self.fig = plt.figure(figsize=(12, 8))
            self.ax = self.fig.add_subplot(111, projection='3d')
            
            # For 2D matrix (64x64): create X, Y meshgrid
            if matrix.ndim == 2:
                rows, cols = matrix.shape
                X = np.arange(cols)
                Y = np.arange(rows)
                X, Y = np.meshgrid(X, Y)
                Z = matrix
            # For 3D matrix (640x64): flatten to 2D by averaging
            elif matrix.ndim == 3:
                Z = np.mean(matrix, axis=0)
                rows, cols = Z.shape
                X = np.arange(cols)
                Y = np.arange(rows)
                X, Y = np.meshgrid(X, Y)
            else:
                # 640x64 case: reshape to 10x64x64
                if matrix.shape == (640, 64):
                    Z = np.mean(matrix.reshape(10, 64, 64), axis=0)
                    rows, cols = Z.shape
                    X = np.arange(cols)
                    Y = np.arange(rows)
                    X, Y = np.meshgrid(X, Y)
                else:
                    logger.error(f"Unexpected matrix shape: {matrix.shape}")
                    return False
            
            # Plot surface
            logger.info("Plotting surface...")
            surf = self.ax.plot_surface(
                X, Y, Z,
                cmap=cm.viridis,           # Color map
                linewidth=0,                # No wireframe lines
                antialiased=True,
                alpha=0.9
            )
            
            # Add colorbar
            colorbar = self.fig.colorbar(surf, ax=self.ax, shrink=0.5)
            colorbar.set_label('Amplitude')
            
            # Labels and title
            self.ax.set_xlabel('Grid X')
            self.ax.set_ylabel('Grid Y')
            self.ax.set_zlabel('Amplitude')
            self.ax.set_title(self.title)
            
            # Add statistics text
            if stats:
                min_all = np.mean(stats.get('min_values', [0]))
                max_all = np.mean(stats.get('max_values', [0]))
                mean_all = np.mean(stats.get('mean_values', [0]))
                
                stats_text = (
                    f"Global Min: {min_all:.4f}\n"
                    f"Global Max: {max_all:.4f}\n"
                    f"Global Mean: {mean_all:.4f}"
                )
                self.fig.text(0.02, 0.98, stats_text, 
                            verticalalignment='top',
                            bbox=dict(boxstyle='round', 
                                    facecolor='wheat', alpha=0.5))
                logger.info(f"Stats: {stats_text.replace(chr(10), ' | ')}")
            
            logger.info("✓ Successfully plotted surface")
            return True
            
        except Exception as e:
            logger.error(f"Error plotting matrix: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def show(self):
        """Display the plot (blocking call)."""
        if self.fig is None:
            logger.error("No plot to display")
            return
        
        logger.info("Displaying plot... (close window to exit)")
        plt.show()
    
    def save(self, filename: str) -> bool:
        """
        Save plot to file.
        
        Args:
            filename: Output filename (e.g., 'wave_plot.png')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.fig is None:
                logger.error("No plot to save")
                return False
            
            self.fig.savefig(filename, dpi=150, bbox_inches='tight')
            logger.info(f"✓ Saved plot to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error saving plot: {e}")
            return False


# ============================================================================
# TEST DATA GENERATION
# ============================================================================

def generate_test_data(buffer: DataBuffer) -> bool:
    """
    Generate sample Schrödinger wave data for dry-run testing.
    
    Creates 10 realistic wave matrices using Gaussian envelope
    with sinusoidal oscillations. Each pod gets a slightly different
    phase to simulate independent computation.
    
    Args:
        buffer: DataBuffer instance to populate
        
    Returns:
        True if all 10 samples generated successfully, False otherwise
    """
    logger.info("\nGenerating sample test data (no Redis required)...")
    logger.info("")
    
    try:
        grid_size = 64
        
        for job_index in range(10):
            # Generate realistic Schrödinger-like wave pattern
            # Using Gaussian envelope * sinusoidal oscillations
            x = np.linspace(-np.pi, np.pi, grid_size)
            y = np.linspace(-np.pi, np.pi, grid_size)
            X, Y = np.meshgrid(x, y)
            
            # Each pod gets a different phase offset (job_index * 0.5)
            phase = job_index * 0.5
            
            # Create wave: Gaussian envelope with sine/cosine modulation
            amplitude = (
                np.exp(-(X**2 + Y**2) / 4) *  # Gaussian envelope
                np.sin(X + phase) *             # X oscillation with phase
                np.cos(Y + phase)               # Y oscillation with phase
            )
            
            # Build payload (same format as parallel_worker.py)
            payload = {
                "job_completion_index": job_index,
                "grid_size": grid_size,
                "amplitude": amplitude.tolist(),  # Full 64x64 matrix
                "min": float(amplitude.min()),
                "max": float(amplitude.max()),
                "mean": float(amplitude.mean()),
            }
            
            # Serialize to JSON (same as Redis message)
            json_message = json.dumps(payload)
            
            # Add to buffer (same as receiving from Redis)
            if not buffer.add_result(json_message):
                logger.error(f"Failed to add test data for pod {job_index}")
                return False
            
            buffer.print_status()
        
        logger.info("")
        logger.info("✓ Test data generated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error generating test data: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """
    Main entry point for the visualizer.
    
    Flow:
    1. Parse command-line arguments
    2. Connect to Redis
    3. Subscribe to results channel
    4. Listen for incoming pod results
    5. When all 10 received, assemble matrix
    6. Plot and display 3D wave
    """
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Schrödinger Wave Equation Visualizer'
    )
    parser.add_argument(
        '--redis-host',
        default='172.31.31.172',
        help='Redis server hostname (default: 172.31.31.172)'
    )
    parser.add_argument(
        '--redis-port',
        type=int,
        default=6379,
        help='Redis server port (default: 6379)'
    )
    parser.add_argument(
        '--redis-password',
        default=None,
        help='Redis password (optional)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=120,
        help='Timeout in seconds waiting for all results (default: 120)'
    )
    parser.add_argument(
        '--save-plot',
        help='Save plot to file (e.g., wave_plot.png)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Use generated sample data instead of Redis (for testing)'
    )
    parser.add_argument(
        '--ssh-host',
        default=None,
        help='EC2 instance hostname/IP for SSH tunnel (optional)'
    )
    parser.add_argument(
        '--ssh-key',
        default=None,
        help='Path to SSH private key file for tunneling (e.g., ~/.ssh/ec2-key.pem)'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("SCHRÖDINGER WAVE VISUALIZER - Starting")
    logger.info("=" * 70)
    
    # Initialize buffer
    buffer = DataBuffer(expected_pods=10, grid_size=64)
    
    # DRY RUN MODE (use generated test data)
    if args.dry_run:
        logger.info("[DRY RUN MODE] Using generated test data")
        if not generate_test_data(buffer):
            logger.error("Fatal: Failed to generate test data")
            return 1
    
    # REDIS MODE (connect to server and listen)
    else:
        # Step 1: Connect to Redis (with optional SSH tunnel)
        subscriber = RedisSubscriber(
            host=args.redis_host,
            port=args.redis_port,
            password=args.redis_password,
            ssh_host=args.ssh_host,
            ssh_key=args.ssh_key,
            ssh_username="ubuntu"
        )
        
        if not subscriber.connect():
            logger.error("Fatal: Could not connect to Redis")
            return 1
        
        # Step 2: Subscribe to results channel
        if not subscriber.subscribe("schrodinger-results"):
            logger.error("Fatal: Could not subscribe to channel")
            return 1
        
        # Step 3: Listen for results
        start_time = time.time()
        message_count = 0
        
        logger.info(f"Waiting for pod results (timeout: {args.timeout}s)...")
        logger.info("")
        
        try:
            for message in subscriber.listen():
                elapsed = time.time() - start_time
                
                # Add result to buffer
                if buffer.add_result(message):
                    message_count += 1
                    buffer.print_status()
                
                # Check if complete
                if buffer.is_complete():
                    logger.info("")
                    logger.info(f"✓ ALL RESULTS RECEIVED!");
                    logger.info(f"  Time elapsed: {elapsed:.1f}s")
                    logger.info(f"  Messages processed: {message_count}")
                    break
                
                # Check timeout
                if elapsed > args.timeout:
                    logger.warning(f"Timeout after {elapsed:.1f}s")
                    logger.warning(f"Received {buffer.received_count}/{buffer.expected_pods} "
                                "results")
                    break
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
    
    # Step 4: Assemble and visualize
    logger.info("")
    logger.info("=" * 70)
    logger.info("ASSEMBLING MATRIX")
    logger.info("=" * 70)
    
    if buffer.is_complete():
        assembled_matrix = buffer.get_assembled_matrix()
        
        if assembled_matrix is not None:
            # Create visualizer
            viz = WaveVisualizer(
                title="Schrödinger Wave Equation - Complete Wave Function"
            )
            
            # Plot
            logger.info("")
            logger.info("=" * 70)
            logger.info("PLOTTING WAVE FUNCTION")
            logger.info("=" * 70)
            logger.info("")
            
            if viz.plot_matrix(assembled_matrix, buffer.all_stats):
                # Save if requested
                if args.save_plot:
                    viz.save(args.save_plot)
                
                # Display
                logger.info("Close the plot window to exit")
                viz.show()
                
                logger.info("✓ Visualization complete")
                return 0
    
    logger.error("✗ Failed to visualize (incomplete data)")
    return 1


if __name__ == "__main__":
    exit(main())
