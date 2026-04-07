# Use Cases

CUTIP is designed for multi-step operations that need containers as execution environments. These are real patterns built with cutip.

---

## 1. VM operations: Remote service configuration

**Problem:** Configuring a remote virtual machine requires multiple steps across multiple tools: SSH into the VM, run setup scripts, fetch Kubernetes secrets, patch a source file inside a running pod, mount it back via hostPath, and verify the deployment rolls out. A bash script does this but breaks silently, has no validation, and can't be inspected.

**Solution:** A cutip project with a single group that runs inside a container with SSH and kubectl access. The workflow uses `@action` decorators and `stage()` separators to create a 3-stage pipeline:

```python
@orchestrator
def main(ctx):
    container.start(ctx, container="ops-runner")

    with ssh.session(ctx, container="ops-runner",
                     host=vm["ip"], username="root", password=pw) as sesh:

        stage("Pre-op Validation", description="Verify SSH, K8s resources, and file integrity")
        validate_ssh(ctx, sesh)
        check_deploy(ctx, sesh, ns, deploy)
        check_secret(ctx, sesh, secret_ns, secret_name)
        check_pod(ctx, sesh, ns, deploy)
        check_source_file(ctx, sesh, ns, deploy, source_file)

        stage("Operations", description="Run setup, fetch credentials, patch deployment")
        run_setup_script(ctx, sesh, script_path)
        fetch_credentials(ctx, sesh, secret_ns, secret_name)
        patch_source(ctx, sesh, ns, deploy, patch_config)
        apply_deploy(ctx, sesh, ns, deploy, volume_config)

        stage("Post-op Validation", description="Confirm patched pod is healthy")
        verify_rollout(ctx, sesh, ns, deploy)

    container.stop(ctx, container="ops-runner")
    container.remove(ctx, container="ops-runner")
```

**What cutip adds over a bash script:**

- Pre-op validation catches missing deployments, secrets, or files before any changes are made
- Each step is a named `@action` visible in the cutip-desktop DAG
- Credentials are managed via `secrets.yaml` with fail-fast validation
- The workflow is Python --- you can add error handling, retry logic, or conditional paths
- Re-runs are safe: the patcher detects previous runs and avoids overwriting valid state

**Blocks used:** `container.start/stop/remove`, `ssh.session`, `ssh.probe`, `k8s.get_deployment`, `k8s.get_secret`, `k8s.get_pod`, `k8s.exec`, `k8s.cp`, `k8s.patch_deployment`, `k8s.rollout_status`, `file.is_empty`

---

## 2. Dev environment: Frontend app container with local dependencies

**Problem:** A frontend application has `file:` dependencies in `package.json` that point to local packages. Building the dev container requires staging these local packages into the build context before the image build, then starting the container with host networking so it can reach backend services.

**Solution:** A cutip project with a prehook that reads `package.json`, copies the local dependencies into the build context, and a workflow that starts the container:

```python
# cutip/units/frontend/prehook.py
def pre_build(ctx):
    pkg = file.read_json(ctx, container="frontend",
                         path=str(ctx.paths["app_repo"] / "package.json"))
    for dep_name, dep_value in pkg.get("dependencies", {}).items():
        if dep_value.startswith("file:"):
            local_path = ctx.paths["app_repo"] / dep_value.replace("file:", "")
            file.copy_tree(ctx, container="frontend",
                          src=str(local_path),
                          dest=str(ctx.project_root / "resources" / "buildtime" / dep_name))
```

```python
# cutip/groups/frontend/workflow.py
@orchestrator
def main(ctx):
    stage("Start")
    container.start(ctx, container="frontend")
```

**What cutip adds:** The prehook runs before the image build. `file:` dependencies are resolved and staged automatically. Without cutip, you'd need a Makefile target or a separate script that you remember to run before `docker build`.

---

## 3. Infrastructure provisioning: Multi-container networking

**Problem:** A distributed application needs 10 containers across 5 groups: a DHCP server with dynamic subnet allocation, a cache server, a backend, a frontend, and multiple client stations --- all on a custom bridge network with specific CIDR ranges. The client containers must wait for the DHCP server to assign IPs before starting.

**Solution:** A cutip project with separate groups for each concern:

- `infra` --- starts the DHCP server, allocates subnets dynamically
- `services` --- starts cache + backend + frontend with health checks
- `clients` --- starts client containers after network is ready

Each group has its own `workflow.py` with startup ordering that depends on actual network readiness, not just `depends_on` declarations. The DHCP server's subnet allocation is Python code in the workflow --- it reads the network state, calculates available CIDRs, and configures the server before starting dependent containers.

**What cutip adds:** Docker Compose can't express "start this container, exec into it to check the network state, then decide which subnet to assign to the next container." Cutip's workflow is Python --- you can read state, branch, and orchestrate based on runtime conditions.

---

## Common patterns across all use cases

1. **Validate before executing.** `cutip validate` catches broken refs, missing secrets, and invalid YAML without touching a container runtime. Run it in CI.

2. **Hooks for build-time logic.** `pre_build(ctx)` generates config files, copies dependencies, and stages secrets into the build context. `startup(ctx)` verifies the deployment after containers start.

3. **Workflows are Python.** No DSL, no templating language, no YAML for logic. Import libraries, call APIs, branch on conditions. Test with pytest.

4. **Visual inspection.** Every `@action` and `stage()` in a workflow is visible as a node in [cutip-desktop](https://github.com/joshuajerome/cutip-desktop)'s DAG view. Click a node to see its code. Click an edge to see the transition.
