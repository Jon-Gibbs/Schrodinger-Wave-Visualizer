import json
import os

import numpy as np
import schrodinger


def get_job_completion_index() -> int:
    value = os.getenv("JOB_COMPLETION_INDEX", "0")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("JOB_COMPLETION_INDEX must be an integer") from exc


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
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
