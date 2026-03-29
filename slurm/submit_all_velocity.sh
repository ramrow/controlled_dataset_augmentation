#!/bin/bash
set -e
cd /mnt/lustre/rpi/pxu10/dataset/slurm
sbatch velocity_chunk_0.slurm
sbatch velocity_chunk_1.slurm
sbatch velocity_chunk_2.slurm
sbatch velocity_chunk_3.slurm
sbatch velocity_chunk_4.slurm
sbatch velocity_chunk_5.slurm
sbatch velocity_chunk_6.slurm
sbatch velocity_chunk_7.slurm
sbatch velocity_chunk_8.slurm
sbatch velocity_chunk_9.slurm
sbatch velocity_chunk_10.slurm
sbatch velocity_chunk_11.slurm
