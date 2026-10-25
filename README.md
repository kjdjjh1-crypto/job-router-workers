# job-router-workers

Private worker repository for the local `job-router` control plane.

The workflow is dispatched with `gh workflow run job.yml`. The router sends a
JSON command and shard coordinates; the worker writes `jr-artifacts/result.json`
and uploads it as an artifact.
