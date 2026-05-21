# BusyBee CPU Policy Report

This report evaluates a non-generative CPU action policy: TF-IDF features plus linear classifiers for action selection and argument-template selection.
Concrete arguments are filled by deterministic resolvers before schema and safety checks.

## examples__eval_synthetic

- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.5600
- argument_semantic_match: 0.5600
- placeholder_rate: 0.0000
- correct_action_and_arg_semantic: 0.5600
- unnecessary_escalation_rate: 0.0000
- unsafe_command_rate: 0.0000
- repeated_action_loop_rate: 0.0000
- json_validity_rate: 1.0000
- strict_json_rate: 1.0000
- concrete_argument_semantic_match: 0.5600
- concrete_argument_rows: 200

### Grouped Metrics

#### edit (n=51)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### escalate (n=37)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### inspect (n=58)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

#### test (n=54)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

## examples__eval

- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 0.9000
- argument_exact_match: 0.6000
- argument_semantic_match: 0.6000
- placeholder_rate: 0.0000
- correct_action_and_arg_semantic: 0.6000
- unnecessary_escalation_rate: 0.0000
- unsafe_command_rate: 0.0000
- repeated_action_loop_rate: 0.0000
- json_validity_rate: 1.0000
- strict_json_rate: 1.0000
- concrete_argument_semantic_match: 0.6000
- concrete_argument_rows: 10

### Grouped Metrics

#### edit (n=1)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

#### escalate (n=1)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### execute (n=1)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

#### inspect (n=2)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

#### memory (n=1)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### other (n=3)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 0.6667
- argument_exact_match: 0.3333
- argument_semantic_match: 0.3333

#### test (n=1)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 1.0000
- argument_semantic_match: 1.0000

## examples__eval_bfcl

- valid_action_rate: 1.0000
- schema_validity_rate: 0.9946
- correct_action_accuracy: 0.4072
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0144
- placeholder_rate: 0.0000
- correct_action_and_arg_semantic: 0.0000
- unnecessary_escalation_rate: 0.5874
- unsafe_command_rate: 0.0000
- repeated_action_loop_rate: 0.0000
- json_validity_rate: 1.0000
- strict_json_rate: 1.0000
- concrete_argument_semantic_match: 0.0000
- concrete_argument_rows: 547

### Grouped Metrics

#### edit (n=28)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 0.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### escalate (n=226)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 1.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000

#### inspect (n=258)
- valid_action_rate: 1.0000
- schema_validity_rate: 0.9884
- correct_action_accuracy: 0.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0310

#### test (n=43)
- valid_action_rate: 1.0000
- schema_validity_rate: 1.0000
- correct_action_accuracy: 0.0000
- argument_exact_match: 0.0000
- argument_semantic_match: 0.0000
