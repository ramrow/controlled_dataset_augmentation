import os
import subprocess
import argparse
import json

WM_PROJECT_DIR = os.environ.get('WM_PROJECT_DIR')
if not WM_PROJECT_DIR:
    print("Error: WM_PROJECT_DIR is not set in the environment.")
    exit(1)

def read_user_requirement(file_path):
    """Reads and returns the content of user_requirement.txt."""
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            content = file.read()
            return content
    else:
        print(f"File not found: {file_path}")
        return ""
    

def run_benchmark(i, algorithm_name, requirements, prompts, indices):
    """Creates user_requirement.txt and runs foambench_main.py."""
    case_name = requirements[i]["case_name"]
    requirement = requirements[i]["user_requirement"]
    folder_path = os.path.abspath(os.path.join("requirements", case_name))
    os.makedirs(folder_path, exist_ok=True)
    requirement_txt_path = os.path.abspath(os.path.join(folder_path, "user_requirement.txt"))
    with open(requirement_txt_path, 'w') as f:
        f.write(requirement)

    output_folder = os.path.abspath(os.path.join(
        "prompts",
        case_name
    ))
    os.makedirs(output_folder, exist_ok=True)

    if i % 2 == 0:
        with open("Foam-Agent/src/number.py", 'w') as f:
            f.write("similar_case_i = 0")
        indices[case_name] = 0
    else:
        with open("Foam-Agent/src/number.py", 'w') as f:
            f.write("similar_case_i = 1")
        indices[case_name] = 1

    command = f"python {algorithm_name}/foambench_main.py --openfoam_path {WM_PROJECT_DIR} --output {output_folder} --prompt_path {requirement_txt_path}"
    print(f"Running: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error on {case_name}: {e}")

    with open(f"{output_folder}/similar_case.txt", 'r') as f:
        prompts[case_name] = f.read()

if __name__ == "__main__":
    """Loops through all datasets and runs benchmarks for cases"""
    parser = argparse.ArgumentParser(description='Run OpenFOAM benchmarks')
    parser.add_argument('--algorithm_name', type=str, default="Foam-Agent", help='Name of the algorithm (same as the directory name in algorithm folder)')
    args = parser.parse_args()
    print(f"Running benchmarks for {args.algorithm_name}")

    with open("distinct-cases-and-requirements.json", 'r') as f:
        requirements = json.load(f)

    prompts = {}
    indices = {}
    N = len(requirements)
    for i in range(N):
        run_benchmark(i, args.algorithm_name, requirements, prompts, indices)
    
    with open("prompts.json", 'w') as f:
        json.dump(prompts, f, indent=4)
    with open("indices.json", 'w') as f:
        json.dump(indices, f, indent=4)