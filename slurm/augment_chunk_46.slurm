#!/bin/bash
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -p rpi
#SBATCH -A rpi
#SBATCH --gres=gpu:nvidia_h100_80gb_hbm3:1
#SBATCH --time=10:00:00
#SBATCH --output=%x_out
#SBATCH --error=%x_err

source /mnt/lustre/rpi/pxu10/agent/bin/activate
source /mnt/lustre/rpi/pxu10/dataset/slurm/aws_env.sh
cd /mnt/lustre/rpi/pxu10/dataset
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 46 --chunk-count 72 --stages velocity,viscosity,density --timeout-sec 2600
