# JSON Status Summary Tool (R1-WORKER-01)

Reads a JSON array (stdin or `--file`). Each element must be an object with a
`status` field of exactly one of `PASS | FAIL | BLOCKED | NOT_TESTED`.
Prints counts for the four statuses as JSON.

- Empty array → `{"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT_TESTED": 0}`, exit 0
- Non-array, missing `status`, unknown `status`, malformed JSON → stderr message, exit **2**

## Usage

```bash
echo '[{"status":"PASS"}]' | python3 status_tool.py
python3 status_tool.py --file sample_fixed.json
python3 test_status_tool.py
```

Python 3 stdlib only; no installation, no network.
