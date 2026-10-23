# aws-lambda-uv

Example Python Lambda functions that [AWS SAM](https://docs.aws.amazon.com/serverless-application-model/) builds with [uv](https://docs.astral.sh/uv/) instead of pip.

There are four functions, each started by a different trigger:

```text
POST /greet ──▶ greet
file into the uploads bucket under incoming/ ──▶ process_upload ──▶ jobs queue ──▶ handle_job
                                                                       │ 3 failed attempts
                                                                       ▼
every day at 06:00 UTC ──▶ nightly_report ──reads──▶ dead-letter queue
```

| Function | Trigger | What it does | Runtime dependencies |
| --- | --- | --- | --- |
| `greet` | HTTP API, `POST /greet` | validates the body and returns a greeting | pydantic |
| `process_upload` | S3 `ObjectCreated` under `incoming/` | puts one job per new file on the jobs queue | none (boto3 is in the runtime) |
| `handle_job` | SQS, batches of up to 10 | processes each job; reports failed messages one by one so only those are retried, then sent to the dead-letter queue after 3 attempts | pydantic |
| `nightly_report` | EventBridge Scheduler, `cron(0 6 * * ? *)` | logs how many jobs are in the dead-letter queue | none (boto3 is in the runtime) |

pydantic was picked because it has a compiled part (`pydantic-core`), which shows uv fetching the right wheels for Lambda. `handle_job` refuses files over 10 MB, so you can see a failing job end up in the dead-letter queue.

## How it works

SAM has a `python-uv` build method. One line on each function in `template.yaml` turns it on:

```yaml
GreetFunction:
  Type: AWS::Serverless::Function
  Metadata:
    BuildMethod: python-uv
  Properties:
    CodeUri: functions/greet/
    Handler: app.handler
```

On `sam build`, SAM finds `pyproject.toml` in `CodeUri`, then:

1. exports `uv.lock` to a requirements list, leaving out dependency groups (so `pytest` never reaches the zip);
2. runs `uv pip install --target` with `--python-platform` set for the function's architecture and `--python-version` from its runtime;
3. copies the source next to the installed packages.

Because uv picks wheels by platform, an `arm64` function builds on an x86_64 machine (or a Mac) without Docker. Check `.aws-sam/build/GreetFunction/pydantic_core/` after a build: the `.so` is `aarch64-linux-gnu`.

`python-uv` is still a SAM beta feature, so SAM asks before every build unless you opt in. This repo opts in twice:

- `samconfig.toml` sets `beta_features = true` for `build`, `sync` and local runs;
- `mise.toml` sets `SAM_CLI_BETA_UV_PACKAGE_MANAGER=1`, which covers every `sam` command, including the per-stage `--config-env` ones.

The [AWS guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/building-python-uv.html) names the variable `SAM_CLI_BETA_PYTHON_UV=1`, but SAM CLI 1.170.0 (the version pinned here) ignores that name and still prompts. `sam build --beta-features` works too.

It needs a recent SAM CLI (this repo pins 1.170.0) and `uv` on your `PATH`.

## Layout

```text
template.yaml                 # all functions, their triggers, the bucket and queues
samconfig.toml                # beta opt-in, build cache, one deploy config per stage
functions/
  greet/                      # one directory per function, each its own uv project:
    pyproject.toml            #   runtime dependencies + a dev group
    uv.lock                   #   what SAM installs into this function's zip
    app.py                    #   the handler
  process_upload/
  handle_job/
  nightly_report/
tests/<function>/test_app.py  # each function's tests, run in that function's environment
events/<function>.json        # a sample event for each function
mise.toml                     # pinned Python, uv, SAM CLI and ruff, plus tasks
```

Each function has its own `pyproject.toml` and `uv.lock`, so each zip only gets the dependencies that function needs: the two boto3 functions deploy as a single `app.py`. `boto3` is a dev dependency in those two, for the tests; in Lambda it comes from the Python runtime. To pin your own boto3 version, move it to `dependencies`.

### Adding a function

1. Copy a directory in `functions/`, rename it (for example `functions/resize_image/`), set `name` in its `pyproject.toml`, and run `uv lock` in it.
2. Add a resource to `template.yaml` named after the directory in PascalCase, with `Function` on the end (`ResizeImageFunction`), with `Metadata: BuildMethod: python-uv`, `CodeUri: functions/resize_image/`, and its trigger under `Events`. Copy one of the log groups too.
3. Add `tests/resize_image/` and `events/resize_image.json`, and add the name to the `choices` in `mise.toml`.

The naming is what `mise run invoke`, `remote` and `logs` rely on to find a function. `mise run install`, `lock` and `test` pick up every directory in `functions/` on their own.

## Usage

[mise](https://mise.jdx.dev) installs the pinned tools:

```bash
mise install
mise run install   # uv sync in every function: creates each one's .venv with its dev tools
mise run test      # each function's tests, in its own environment
mise run lint      # ruff
mise run build     # sam build: one zip per function
```

Without mise you need Python 3.14, uv and the SAM CLI; the tasks in `mise.toml` show the plain commands.

Add a dependency with uv, then rebuild:

```bash
cd functions/greet
uv add httpx           # updates pyproject.toml and uv.lock
uv add --dev moto      # dev only: never deployed
```

### Run it locally

Needs Docker. SAM runs the built zip inside the real Lambda runtime image, with the function's sample event from `events/`.

```bash
mise run invoke greet
mise run invoke handle_job
mise run api       # sam local start-api, then:
curl -X POST http://127.0.0.1:3000/greet -d '{"name": "Ada", "excited": true}'
```

`process_upload` and `nightly_report` call SQS, so locally they need AWS credentials and real queue URLs. Deploy a stage first and use `mise run remote` instead.

The functions are `arm64`, so on an x86_64 machine Docker needs arm64 emulation (Docker Desktop has it; on Linux, install `qemu-user-static`). On an Apple Silicon Mac they run natively.

## Stages

There are four stages: `dev`, `test`, `stage` and `prod`. Each is its own CloudFormation stack built from the same template, with the `Stage` parameter set:

| Stage | Stack | Log level | Log retention | Nightly schedule | Asks before deploying |
| --- | --- | --- | --- | --- | --- |
| dev | `aws-lambda-uv-dev` | DEBUG | 7 days | off | no |
| test | `aws-lambda-uv-test` | DEBUG | 7 days | off | no |
| stage | `aws-lambda-uv-stage` | DEBUG | 7 days | off | yes |
| prod | `aws-lambda-uv-prod` | INFO | 90 days | on | yes |

Every resource is named after its stack, so the stages never clash: `aws-lambda-uv-dev-greet`, `aws-lambda-uv-prod-jobs`, `aws-lambda-uv-test-uploads-<account id>` and so on. Each function gets the stage in its `STAGE` environment variable; `greet` returns it in the response. Logs are JSON, at the level in the table. Per-stage differences live in `template.yaml` (`!If [IsProd, ...]`), and per-stage deploy settings in `samconfig.toml`.

They all deploy to the account and region of your current AWS credentials. To put a stage in its own account, add `profile = "<profile>"` and `region = "<region>"` to its `[<stage>.deploy.parameters]` section.

### Deploy

Needs AWS credentials and a region (`AWS_REGION` or your profile's default).

```bash
mise run deploy dev     # sam build, then sam deploy --config-env dev
mise run deploy prod    # shows the change set and asks before applying it
mise run sync           # sam sync --watch to dev: pushes code changes as you save
```

The stack outputs give each stage's API URL, bucket and queue URLs.

### Try the triggers

```bash
mise run remote dev greet          # sam remote invoke with events/greet.json
aws s3 cp report.csv s3://aws-lambda-uv-dev-uploads-<account id>/incoming/report.csv
mise run logs dev process_upload   # see the job get queued...
mise run logs dev handle_job       # ...and processed
mise run remote dev nightly_report # the schedule only runs in prod; run it by hand elsewhere
```

Upload a file over 10 MB and `handle_job` fails it three times, after which SQS moves it to the dead-letter queue and the next `nightly_report` warns about it.

Remove a stage with `mise run delete <stage>`. CloudFormation can't delete a bucket with files in it, so empty the uploads bucket first.
