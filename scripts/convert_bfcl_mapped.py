#!/usr/bin/env python3
"""
Convert BFCL V3 dataset to busyBee-cpu JSONL format with category mapping.

Maps BFCL's 569 unique function names to busyBee-cpu's 4 core tool categories:
- read_file: Find/Search/Lookup/Get operations (retrieve information)
- run_tests: Calculate/Compute/Execute operations (run computations)
- apply_patch: Book/Buy/Reserve/Make/Update operations (make changes)
- escalate: Irrelevance scenarios or security-sensitive operations

This reduces the classification problem from 569 classes to 4, making it
tractable for the TF-IDF + VotingClassifier pipeline.

Total: ~2,775 examples across 4 balanced categories.
"""

import json
import random
import re
from pathlib import Path
from typing import Any


# Keywords that map to each busyBee-cpu tool category
CATEGORY_PATTERNS = {
    "read_file": [
        r"find", r"search", r"lookup", r"get", r"list", r"show", r"display",
        r"check", r"query", r"fetch", r"retrieve", r"view", r"read",
        r"weather", r"forecast",  # Weather lookups
        r"attraction", r"movie", r"music", r"event",  # Entertainment lookups
    ],
    "run_tests": [
        r"calculate", r"compute", r"sum", r"average", r"mean", r"median",
        r"factorial", r"area", r"volume", r"distance", r"convert",
        r"triangle", r"circle", r"rectangle",  # Geometry calculations
        r"execute", r"run", r"test", r"validate",
    ],
    "apply_patch": [
        r"book", r"buy", r"purchase", r"reserve", r"order", r"add",
        r"update", r"modify", r"change", r"set", r"create", r"make",
        r"send", r"post", r"submit", r"upload",
        r"delete", r"remove", r"cancel",
        r"payment", r"pay", r"transfer",
    ],
}

# Security-sensitive patterns that should always escalate
SECURITY_PATTERNS = [
    r"attack", r"exploit", r"phish", r"bypass", r"scanner\.scan",
    r"osint", r"shodan", r"subdomain", r"xss", r"sql_injection",
    r"crawler", r"encrypt", r"decrypt", r"crypto",
]


def classify_function(func_name: str, func_desc: str = "") -> str:
    """
    Classify a BFCL function name into a busyBee-cpu tool category.
    
    Returns one of: read_file, run_tests, apply_patch, escalate
    """
    func_lower = func_name.lower()
    desc_lower = func_desc.lower() if func_desc else ""
    combined = f"{func_lower} {desc_lower}"
    
    # Check security patterns first (always escalate)
    for pattern in SECURITY_PATTERNS:
        if re.search(pattern, func_lower):
            return "escalate"
    
    # Check category patterns
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, combined):
                return category
    
    # Default to escalate for unknown functions
    return "escalate"


def load_bfcl_file(path: Path) -> list[dict]:
    """Load a BFCL JSONL file."""
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    return examples


def load_possible_answers(path: Path) -> dict[str, dict]:
    """Load possible answers file, keyed by id."""
    answers = {}
    if not path.exists():
        return answers
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                answer = json.loads(line)
                answers[answer["id"]] = answer
    return answers


def extract_ground_truth_category(
    ground_truth: list[dict],
    available_functions: list[dict],
) -> str:
    """
    Extract the target tool category from BFCL ground truth.
    
    Maps the specific BFCL function name to a busyBee-cpu category.
    """
    if not ground_truth:
        return "escalate"
    
    # Get the function name from ground truth
    call = ground_truth[0]
    func_name = list(call.keys())[0]
    
    # Find the function description from available_functions
    func_desc = ""
    for func in available_functions:
        if func["name"] == func_name:
            func_desc = func.get("description", "")
            break
    
    # Classify into busyBee-cpu category
    return classify_function(func_name, func_desc)


def convert_bfcl_schema_to_simple(func_schema: dict) -> dict[str, str]:
    """Convert BFCL function schema to busyBee-cpu's simple name→type mapping."""
    simple_schema = {}
    params = func_schema.get("parameters", {})
    properties = params.get("properties", {})
    
    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "string")
        if param_type == "dict":
            param_type = "object"
        elif param_type == "list":
            param_type = "array"
        simple_schema[param_name] = param_type
    
    return simple_schema


def convert_bfcl_example(
    bfcl_example: dict,
    possible_answers: dict[str, dict],
    source: str,
) -> dict[str, Any] | None:
    """Convert a single BFCL example to busyBee-cpu JSONL format."""
    try:
        # Extract prompt
        question = bfcl_example["question"]
        if not question or not question[0] or not question[0][0]:
            return None
        goal = question[0][0]["content"]
        
        # Extract available tools (keep original BFCL functions for context)
        bfcl_functions = bfcl_example.get("function", [])
        available_tools = []
        
        for func in bfcl_functions:
            tool = {
                "name": func["name"],
                "schema": convert_bfcl_schema_to_simple(func),
            }
            available_tools.append(tool)
        
        # Always add escalate tool
        available_tools.append({
            "name": "escalate",
            "schema": {"reason": "string"},
        })
        
        # Extract ground truth and map to category
        example_id = bfcl_example["id"]
        if example_id in possible_answers:
            ground_truth = possible_answers[example_id].get("ground_truth", [])
            target_tool = extract_ground_truth_category(ground_truth, bfcl_functions)
            
            # Extract args (take first value from each parameter array)
            call = ground_truth[0]
            func_name = list(call.keys())[0]
            params = call[func_name]
            target_args = {}
            for param_name, values in params.items():
                if isinstance(values, list) and values:
                    target_args[param_name] = values[0]
                else:
                    target_args[param_name] = values
        else:
            # No ground truth = irrelevance scenario → escalate
            target_tool = "escalate"
            target_args = {"reason": "No relevant function available for this request"}
        
        # Build busyBee-cpu example
        busybee_example = {
            "id": f"bfcl-{source}-{example_id}",
            "goal": goal,
            "state": {
                "recent_observations": [f"BFCL {source} scenario"],
                "policy_features": {
                    "candidate_paths": [],
                    "candidate_test_command": "",
                },
            },
            "available_tools": available_tools,
            "target_action": {
                "tool": target_tool,
                "args": target_args,
            },
        }
        
        return busybee_example
    
    except Exception as e:
        print(f"  Warning: Failed to convert {bfcl_example.get('id', 'unknown')}: {e}")
        return None


def main():
    random.seed(42)
    
    data_dir = Path("data/bfcl_v3")
    output_dir = Path("examples")
    
    # Define files to process
    files_config = [
        ("BFCL_v3_simple.json", "simple"),
        ("BFCL_v3_multiple.json", "multiple"),
        ("BFCL_v3_irrelevance.json", "irrelevance"),
        ("BFCL_v3_live_multiple.json", "live_multiple"),
        ("BFCL_v3_live_irrelevance.json", "live_irrelevance"),
    ]
    
    all_examples = []
    
    for fname, source in files_config:
        bfcl_path = data_dir / fname
        answers_path = data_dir / "possible_answer" / fname
        
        if not bfcl_path.exists():
            print(f"Skipping {fname}: file not found")
            continue
        
        print(f"Processing {fname}...")
        bfcl_examples = load_bfcl_file(bfcl_path)
        possible_answers = load_possible_answers(answers_path)
        
        converted = []
        for bfcl_ex in bfcl_examples:
            busybee_ex = convert_bfcl_example(bfcl_ex, possible_answers, source)
            if busybee_ex:
                converted.append(busybee_ex)
        
        print(f"  Converted {len(converted)}/{len(bfcl_examples)} examples")
        all_examples.extend(converted)
    
    print(f"\nTotal converted: {len(all_examples)} examples")
    
    # Shuffle and split
    random.shuffle(all_examples)
    split_idx = int(len(all_examples) * 0.8)
    train_examples = all_examples[:split_idx]
    eval_examples = all_examples[split_idx:]
    
    print(f"Train: {len(train_examples)} examples")
    print(f"Eval: {len(eval_examples)} examples")
    
    # Write JSONL files
    train_path = output_dir / "train_bfcl.jsonl"
    eval_path = output_dir / "eval_bfcl.jsonl"
    
    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    with open(eval_path, "w", encoding="utf-8") as f:
        for ex in eval_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    print(f"\nWrote {train_path}")
    print(f"Wrote {eval_path}")
    
    # Print category distribution
    category_counts = {}
    for ex in all_examples:
        tool = ex["target_action"]["tool"]
        category_counts[tool] = category_counts.get(tool, 0) + 1
    
    print("\nTarget category distribution:")
    for category, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(all_examples)
        print(f"  {category}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
