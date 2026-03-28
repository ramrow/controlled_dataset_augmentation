import argparse
import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
from tqdm import tqdm


def load_jsonl_data(file_path: Path) -> List[Dict]:
    """Load data from JSONL file"""
    print(f"Loading jsonl data from {file_path}")
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def main():
    for dataset in ["test", "train"]:
        foamgpt_input_data = load_jsonl_data(f"foamgpt_{dataset}.jsonl")
        print(f"Loaded {len(foamgpt_input_data)} input data")

        output_data = []

        with open("prompts.json", 'r') as f:
            prompts = json.load(f)

        with open("indices.json", 'r') as f:
            indices = json.load(f)

        for case_file_data in foamgpt_input_data:
            case_name = case_file_data['case_name']
            file_name = case_file_data['file_name']
            folder_name = case_file_data['folder_name']
            case_solver = case_file_data['case_solver']
            case_domain = case_file_data['case_domain']
            case_category = case_file_data['case_category']
            case_user_requirement = case_file_data['user_requirement']

            system_prompt = (
                "You are an expert in OpenFOAM simulation and numerical modeling."
                f"Your task is to generate a complete and functional file named: <file_name>{file_name}</file_name> within the <folder_name>{folder_name}</folder_name> directory. "
                "Before finalizing the output, ensure:\n"
                "- Ensure units and dimensions are correct** for all physical variables.\n"
                f"- Ensure case solver settings are consistent with the user's requirements. Available solvers are: {case_solver}.\n"
                "Provide only the code—no explanations, comments, or additional text."
            )

            similar_case = prompts[case_name]
            similar_case_index = indices[case_name]

            user_prompt = (
                f"User requirement: {case_user_requirement}\n"
                f"Refer to the following similar case file content to ensure the generated file aligns with the user requirement:\n<similar_case_reference>{similar_case}</similar_case_reference>\n"
                f"Similar case reference is always correct. If you find the user requirement is very consistent with the similar case reference, you should use the similar case reference as the template to generate the file."
                f"Just modify the necessary parts to make the file complete and functional."
                "Please ensure that the generated file is complete, functional, and logically sound."
                "Additionally, apply your domain expertise to verify that all numerical values are consistent with the user's requirements, maintaining accuracy and coherence."
            )

            output_data.append({
                "case_name": case_name,
                "file_name": file_name,
                "folder_name": folder_name,
                "case_solver": case_solver,
                "case_domain": case_domain,
                "case_category": case_category,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "file_content": case_file_data['file_content'],
                "user_requirement": case_user_requirement,
                "similar_case_index": similar_case_index
            })

        with open(f"{dataset}.jsonl", 'w', encoding='utf-8') as f:
            for data in output_data:
                json.dump(data, f, ensure_ascii=False)
                f.write('\n')
            
            print(f"Saved {len(output_data)} data to {dataset}.jsonl'")

if __name__ == "__main__":
    main()
    