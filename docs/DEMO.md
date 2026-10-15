# Try the evidence loop in 60 seconds

After cloning the repository, run with Python 3.11 or newer:

```sh
python -m pip install -e .
python tools/demo.py
```

No AWS credentials, model key, Docker, Terraform or Hermes is required.
Package installation downloads dependencies; the demo itself runs offline. The sample reuses deterministic rule/comparison code in a disposable
local directory. It ignores the S3 storage setting and removes temporary records
on exit. No cloud or model calls occur.

See an example SSH exposure, its finding, an illustrative operator action,
and comparison with a second synthetic snapshot. All data is synthetic; no
remediation runs. This is an evidence-loop demo, not a simulated live agent
answer or test of your account. It does not demonstrate the full knowledge,
case-tracking or reasoning experience.

For that experience, choose [workstation or AWS setup](../START-HERE.md), provide
your own model access and connect a scoped AWS target.
