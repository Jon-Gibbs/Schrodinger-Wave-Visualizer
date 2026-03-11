import json
import os

import numpy as np
import redis
import schrodinger


def get_job_completion_index() -> int:
    value = os.getenv("JOB_COMPLETION_INDEX", "0")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("JOB_COMPLETION_INDEX must be an integer") from exc


def get_redis_client() -> redis.Redis:
    """Connect to Redis server using environment variables."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", None)
    
    return redis.StrictRedis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        decode_responses=True,
    )


def main() -> None:
    job_index = get_job_completion_index()
    grid_size = int(os.getenv("GRID_SIZE", "64"))
    h_bar = float(os.getenv("H_BAR", "1.0"))
    mass = float(os.getenv("MASS", "1.0"))

    # f2py intent(inout) expects Fortran-contiguous arrays.
    amplitude = np.zeros((grid_size, grid_size), dtype=np.float64, order="F")

    # f2py nests module procedures under the Fortran module name.
    # schrodinger_mod.compute_wave_matrix updates amplitude in-place.
    schrodinger.schrodinger_mod.compute_wave_matrix(
        amplitude,
        job_index,
        h_bar,
        mass,
    )

    payload = {
        "job_completion_index": job_index,
        "grid_size": grid_size,
        "min": float(amplitude.min()),
        "max": float(amplitude.max()),
        "mean": float(amplitude.mean()),
    }
    
    # Serialize payload to JSON
    payload_json = json.dumps(payload)
    print(f"Computed result for job index {job_index}: {payload_json}")
    
    # Publish to Redis
    try:
        redis_client = get_redis_client()
        channel = os.getenv("REDIS_CHANNEL", "schrodinger-results")
        redis_client.publish(channel, payload_json)
        print(f"Published to Redis channel '{channel}'")
    except Exception as e:
        print(f"Warning: Failed to publish to Redis: {e}")
        print("Continuing anyway (computed result printed above)")


if __name__ == "__main__":
    main()
