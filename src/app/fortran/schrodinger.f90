module schrodinger_mod
    use, intrinsic :: iso_c_binding, only: c_double

contains

    ! The main subroutine exposed to Python via f2py
    subroutine compute_wave_matrix(size_n, matrix, num_steps, h_bar, mass)
        implicit none
        
        ! Scalar Inputs from Python (intent(in))
        integer, intent(in) :: size_n, num_steps
        real(c_double), intent(in) :: h_bar, mass
        
        ! 2D Array Output (intent(inout))
        real(c_double), intent(inout) :: matrix(size_n, size_n)
        
        ! Local variables
        integer :: i, j
        real(c_double) :: dx, dy, wave_value
        real(c_double) :: x, y, phase

        dx = 1.0_c_double / real(size_n - 1, c_double)
        dy = 1.0_c_double / real(size_n - 1, c_double)
        
        do i = 1, size_n
            do j = 1, size_n
                x = (i - 1) * dx
                y = (j - 1) * dy
                phase = real(num_steps, c_double) * h_bar / max(mass, 1.0d-12)
                
                ! Compute a simple Gaussian-like wave function approximation
                wave_value = exp(-100.0_c_double * ((x - 0.5_c_double)**2 + (y - 0.5_c_double)**2))
                
                ! Store result in the Fortran array
                matrix(i, j) = wave_value * sin(phase)
            end do
        end do
        
    end subroutine compute_wave_matrix

end module schrodinger_mod