# aws-lambda-uv

An example Python Lambda function that [AWS SAM](https://docs.aws.amazon.com/serverless-application-model/) builds with [uv](https://docs.astral.sh/uv/) instead of pip.

It's a small HTTP API (`POST /greet`) that validates its input with pydantic. pydantic was picked because it has a compiled part (`pydantic-core`), which shows uv fetching the right wheels for Lambda.

## How it works

SAM has a `python-uv` build method. One line in `template.yaml` turns it on:

```yaml
HelloWorldFunction:
  Type: AWS::Serverless::Function
  Metadata:
    BuildMethod: python-uv
  Properties:
    CodeUri: functions/hello_world/
    Handler: app.handler
```

On `sam build`, SAM finds `pyproject.toml` in `CodeUri`, then:

1. exports `uv.lock` to a requirements list, leaving out dependency groups (so `pytest` and `ruff` never reach the zip);
2. runs `uv pip install --target` with `--python-platform` set for the function's architecture and `--python-version` from its runtime;
3. copies the source next to the installed packages.

Because uv picks wheels by platform, an `arm64` function builds on an x86_64 machine (or a Mac) without Docker. Check `.aws-sam/build/HelloWorldFunction/pydantic_core/` after a build: the `.so` is `aarch64-linux-gnu`.

`python-uv` is still a SAM beta feature, so SAM asks before every build unless you opt in. This repo opts in twice:

- `samconfig.toml` sets `beta_features = true` for `build`, `sync` and local runs;
- `mise.toml` sets `SAM_CLI_BETA_UV_PACKAGE_MANAGER=1`, which covers every `sam` command, including the per-stage `--config-env` ones.

The [AWS guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/building-python-uv.html) names the variable `SAM_CLI_BETA_PYTHON_UV=1`, but SAM CLI 1.170.0 (the version pinned here) ignores that name and still prompts. `sam build --beta-features` works too.

It needs a recent SAM CLI (this repo pins 1.170.0) and `uv` on your `PATH`.

## Layout

```text
template.yaml                    # SAM template: function, HTTP API, BuildMethod: python-uv
samconfig.toml                   # beta opt-in, build cache, one deploy config per stage
functions/hello_world/
  pyproject.toml                 # runtime dependencies + a dev group
  uv.lock                        # what SAM installs
  app.py                         # the handler
tests/test_app.py                # unit tests, run against the function's own environment
events/greet.json                # sample API Gateway event for sam local invoke
mise.toml                        # pinned Python, uv and SAM CLI, plus tasks
```

Each function is its own uv project, with its own `pyproject.toml` and `uv.lock`, so each zip only gets that function's dependencies. To add a second function, copy `functions/hello_world`, give it a new name in its `pyproject.toml`, and add a resource with its own `CodeUri`.

## Usage

[mise](https://mise.jdx.dev) installs the pinned tools:

```bash
mise install
mise run install   # uv sync: creates functions/hello_world/.venv with the dev tools
mise run test
mise run lint
mise run build     # sam build
```

Without mise you need Python 3.14, uv and the SAM CLI; the tasks in `mise.toml` show the plain commands.

Add a dependency with uv, then rebuild:

```bash
cd functions/hello_world
uv add httpx           # updates pyproject.toml and uv.lock
uv add --dev moto      # dev only: never deployed
```

### Run it locally

Needs Docker. SAM runs the built zip inside the real Lambda runtime image.

```bash
mise run invoke    # sam local invoke with events/greet.json
mise run api       # sam local start-api, then:
curl -X POST http://127.0.0.1:3000/greet -d '{"name": "Ada", "excited": true}'
```

The function is `arm64`, so on an x86_64 machine Docker needs arm64 emulation (Docker Desktop has it; on Linux, install `qemu-user-static`). On an Apple Silicon Mac it runs natively.

## Stages

There are four stages: `dev`, `test`, `stage` and `prod`. Each is its own CloudFormation stack built from the same template, with the `Stage` parameter set:

| Stage | Stack | Function | Log level | Log retention | Asks before deploying |
| --- | --- | --- | --- | --- | --- |
| dev | `aws-lambda-uv-dev` | `hello-world-dev` | DEBUG | 7 days | no |
| test | `aws-lambda-uv-test` | `hello-world-test` | DEBUG | 7 days | no |
| stage | `aws-lambda-uv-stage` | `hello-world-stage` | DEBUG | 7 days | yes |
| prod | `aws-lambda-uv-prod` | `hello-world-prod` | INFO | 90 days | yes |

The function gets the stage in its `STAGE` environment variable and returns it in the response. Per-stage differences live in `template.yaml` (`!If [IsProd, ...]`), and per-stage deploy settings in `samconfig.toml`.

They all deploy to the account and region of your current AWS credentials. To put a stage in its own account, add `profile = "<profile>"` and `region = "<region>"` to its `[<stage>.deploy.parameters]` section.

### Deploy

Needs AWS credentials and a region (`AWS_REGION` or your profile's default).

```bash
mise run deploy dev     # sam build, then sam deploy --config-env dev
mise run deploy prod    # shows the change set and asks before applying it
mise run sync           # sam sync --watch to dev: pushes code changes as you save
```

The `GreetUrl` output is each stage's endpoint. Remove a stage with `mise run delete <stage>`.
