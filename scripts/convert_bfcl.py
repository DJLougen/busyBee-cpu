#!/usr/bin/env python3
"""
Convert BFCL (Berkeley Function Calling Leaderboard) V3 dataset to busyBee-cpu JSONL format.

Downloads and converts:
- BFCL_v3_simple.json (400 examples) - single function, deterministic
- BFCL_v3_multiple.json (200 examples) - pick 1 of 2-4 functions
- BFCL_v3_irrelevance.json (240 examples) - no function should be called → escalate
- BFCL_v3_live_multiple.json (1053 examples) - production APIs, pick 1 of several
- BFCL_v3_live_irrelevance.json (882 examples) - live APIs, none relevant → escalate

Total: ~2,775 examples

Output:
- examples/train_bfcl.jsonl (80% of data)
- examples/eval_bfcl.jsonl (20% of data)
"""

import json
import random
from pathlib import Path
from typing import Any


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


def extract_ground_truth(ground_truth: list[dict]) -> tuple[str, dict[str, Any]]:
    """
    Extract function name and args from BFCL ground truth.
    
    BFCL ground_truth format: [{"function_name": {"param1": [val1, ...], "param2": [val1, ...]}}]
    We take the first value from each parameter's array.
    """
    if not ground_truth:
        return "escalate", {"reason": "No ground truth available"}
    
    # Take first function call
    call = ground_truth[0]
    func_name = list(call.keys())[0]
    params = call[func_name]
    
    # Flatten args: take first value from each parameter array
    args = {}
    for param_name, values in params.items():
        if isinstance(values, list) and values:
            args[param_name] = values[0]
        else:
            args[param_name] = values
    
    return func_name, args


def convert_bfcl_schema_to_simple(func_schema: dict) -> dict[str, str]:
    """
    Convert BFCL function schema to busyBee-cpu's simple name→type mapping.
    
    BFCL: {"type": "dict", "properties": {"param1": {"type": "integer", ...}, ...}}
    busyBee: {"param1": "integer", "param2": "string"}
    """
    simple_schema = {}
    params = func_schema.get("parameters", {})
    properties = params.get("properties", {})
    
    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "string")
        # Normalize types
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
    """
    Convert a single BFCL example to busyBee-cpu JSONL format.
    
    Returns None if conversion fails (e.g., malformed data).
    """
    try:
        # Extract prompt
        question = bfcl_example["question"]
        if not question or not question[0] or not question[0][0]:
            return None
        goal = question[0][0]["content"]
        
        # Extract available tools from BFCL function definitions
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
        
        # Extract ground truth
        example_id = bfcl_example["id"]
        if example_id in possible_answers:
            ground_truth = possible_answers[example_id].get("ground_truth", [])
            target_tool, target_args = extract_ground_truth(ground_truth)
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
    
    # Print stats
    tool_counts = {}
    for ex in all_examples:
        tool = ex["target_action"]["tool"]
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    
    print("\nTarget tool distribution:")
    for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {tool}: {count}")
    
    # Count escalate
    escalate_count = tool_counts.get("escalate", 0)
    print(f"\nEscalate (irrelevance): {escalate_count} ({100*escalate_count/len(all_examples):.1f}%)")


if __name__ == "__main__":
    main()
