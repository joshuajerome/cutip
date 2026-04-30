"""Background daemon spawning for ``cutip run --bg``.

Cross-platform via subprocess (no fork/exec). The parent process:

  1. Creates ``~/.cutip/processes/<cu-id>/`` with initial meta.json
  2. Spawns a detached child: ``cutip --bg-daemon <cu-id>``
  3. Prints the cu-id and exits

The detached child re-reads the meta, redirects stdout/stderr to log files,
runs the workflow, and updates meta on exit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cutip import processes


def spawn_daemon(
    cu_id: str,
    project_path: Path,
    workflow_path: Path,
    *,
    hosts_path: str | None = None,
) -> int:
    """Fork a detached cutip process to run the workflow in the background.

    Returns the spawned PID. Writes initial meta.json before spawn.
    Caller is responsible for printing the cu-id to the user.
    """
    import subprocess

    # Initial meta — daemon will update once it starts
    meta = processes.Meta(
        cu_id=cu_id,
        project=project_path.stem,
        project_path=str(project_path.resolve()),
        workflow_path=str(workflow_path.resolve()),
        cwd=str(Path.cwd()),
        started_at=processes.now_iso(),
        status="starting",
    )
    processes.write_meta(meta)

    # Build the child command. We invoke cutip itself with a hidden flag.
    # Using `python -m cutip` rather than the `cutip` script is the most
    # portable: works whether installed in a venv, with `uv tool install`,
    # or via editable install. sys.executable points at the same Python.
    python_exe = sys.executable
    if sys.platform == "win32":
        # Prefer pythonw.exe (windowless) over python.exe (console subsystem).
        # python.exe spawns a flashing/persistent PowerShell-style console
        # window even with DETACHED_PROCESS. pythonw.exe ships with every
        # standard Python install on Windows.
        pythonw = Path(python_exe).with_name("pythonw.exe")
        if pythonw.exists():
            python_exe = str(pythonw)

    cmd = [python_exe, "-m", "cutip", "--bg-daemon", cu_id]
    if hosts_path:
        cmd.extend(["--hosts", hosts_path])

    # Open log files now so the daemon can dup2 onto them
    stdout_f = open(processes.stdout_path(cu_id), "ab", buffering=0)
    stderr_f = open(processes.stderr_path(cu_id), "ab", buffering=0)

    try:
        if sys.platform == "win32":
            # Windows: detach via creation flags. No fork needed.
            # DETACHED_PROCESS — don't inherit parent's console
            # CREATE_NEW_PROCESS_GROUP — own process group (so signals don't
            #   propagate from the parent's Ctrl-C)
            # CREATE_NO_WINDOW — extra belt-and-suspenders to suppress any
            #   console window (in case pythonw fallback to python.exe)
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            creationflags = (
                DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            )
            popen = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=str(Path.cwd()),
                close_fds=True,
                creationflags=creationflags,
            )
        else:
            # Unix: start_new_session=True detaches from controlling terminal
            popen = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=str(Path.cwd()),
                close_fds=True,
                start_new_session=True,
            )
    finally:
        # Parent doesn't need the file handles — daemon has its own copies via dup
        stdout_f.close()
        stderr_f.close()

    processes.update_meta(cu_id, host_pid=popen.pid)
    return popen.pid


def run_daemon(cu_id: str, hosts_path_arg: str | None = None) -> int:
    """Daemon entry point. Called by ``cutip --bg-daemon <cu-id>``.

    Reads meta, runs the workflow, updates meta on exit.
    Returns an exit code suitable for sys.exit().
    """
    import yaml

    # Force UTF-8 on the redirected stdout/stderr. On Windows, when stdout
    # is redirected to a file, Python defaults to the locale encoding
    # (cp1252) which can't encode common Unicode glyphs (── ✓ → ⚠ etc.) we
    # use in workflow output. errors='replace' is a safety net so any
    # unexpected byte still doesn't crash the daemon.
    #
    # line_buffering=True forces a flush on every newline. Without this,
    # Python uses block buffering when stdout is a file (~8KB), which
    # means `cutip ps logs` sees nothing for long stretches even though
    # the daemon is actively writing.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, ValueError):
        # Older Python or non-text streams — leave alone.
        pass

    try:
        meta = processes.read_meta(cu_id)
    except FileNotFoundError:
        # Nothing we can do — log to stderr (which is the redirected log file)
        print(f"[daemon] no meta found for cu-id {cu_id}", file=sys.stderr)
        return 2

    processes.update_meta(cu_id, status="running")

    # Expose cu-id to workflow code so ctx.exec_tracked() can register
    # remote PIDs against this run for cascade-kill on `cutip ps stop`.
    os.environ["CUTIP_BG_CU_ID"] = cu_id

    # Install SIGTERM handler so `cutip ps stop` can interrupt us cleanly.
    # Without this, a SIGTERM from the parent kills us mid-action and the
    # meta.json never transitions out of "running".
    import signal as _sig

    def _on_sigterm(signum, frame):
        processes.update_meta(
            cu_id,
            status="stopped",
            finished_at=processes.now_iso(),
            error="received SIGTERM",
        )
        # Re-raise as KeyboardInterrupt so any in-flight `try:` cleanup runs
        raise KeyboardInterrupt("stop requested")

    if sys.platform != "win32":
        _sig.signal(_sig.SIGTERM, _on_sigterm)

    project_path = Path(meta.project_path)
    workflow_path = Path(meta.workflow_path)

    # Re-establish the working directory the user invoked from. Workflow code
    # often references relative paths.
    try:
        os.chdir(meta.cwd)
    except OSError:
        pass

    # Load config + hosts the same way cmd_run does
    from cutip.paths import merge_paths_into_data

    with open(project_path) as f:
        config = yaml.safe_load(f) or {}
    merge_paths_into_data(config, project_path)

    hosts: dict | None = None
    resolved_hosts: dict | None = None
    if hosts_path_arg:
        hp = Path(hosts_path_arg)
    else:
        # Honor data.hosts in the project YAML
        data_hosts = (config.get("data") or {}).get("hosts", "hosts.yaml")
        hp = project_path.parent / data_hosts
    if hp.exists():
        from cutip import hosts as _hosts_mod

        with open(hp) as f:
            hosts = yaml.safe_load(f) or {}
        try:
            resolved_hosts = _hosts_mod.resolve(hp)
        except _hosts_mod.HostsError as e:
            print(f"[daemon] hosts resolve error: {e}", file=sys.stderr)

    # Import the workflow module
    import importlib.util

    spec = importlib.util.spec_from_file_location("workflow", str(workflow_path))
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(project_path.parent))
    spec.loader.exec_module(module)

    # Detect decorator-based workflow
    from cutip.workflow.decorators import _ACTION_ATTR

    has_actions = any(
        hasattr(getattr(module, attr, None), _ACTION_ATTR)
        for attr in dir(module)
        if callable(getattr(module, attr, None))
    )

    exit_code = 0
    error_msg: str | None = None

    try:
        if has_actions:
            from cutip.workflow.engine import WorkflowEngine, ActionFailed, ActionEvent

            def on_event(event: ActionEvent) -> None:
                # Daemon stdout is already redirected to stdout.log — print is enough
                if event.event == "stage_started":
                    print(f"\n── {event.action} ──")
                elif event.event == "action_started":
                    label = f"  ▶ {event.action}"
                    if event.attempt > 1:
                        label += f" (attempt {event.attempt})"
                    print(label)
                elif event.event == "action_completed":
                    print(f"  ✓ {event.action}")
                elif event.event == "action_failed":
                    print(f"  ✗ {event.action}: {event.error}", file=sys.stderr)
                elif event.event == "action_retrying":
                    print(f"  ↻ {event.action} — {event.detail}")
                elif event.event == "action_skipped":
                    print(f"  ○ {event.action} (skipped)")

            engine = WorkflowEngine(module, config, on_event=on_event, hosts=hosts)
            if resolved_hosts is not None:
                engine.ctx._resolved_hosts = resolved_hosts
            try:
                engine.run()
            except ActionFailed as e:
                error_msg = str(e)
                exit_code = 1
        elif hasattr(module, "run_standalone"):
            module.run_standalone(config)
        elif hasattr(module, "main"):
            module.main(config)
        else:
            error_msg = "workflow has no @action functions, run_standalone(), or main()"
            exit_code = 1
    except KeyboardInterrupt:
        # Raised by SIGTERM handler. Meta already updated to "stopped".
        processes.clear_stop(cu_id)
        return 130
    except Exception as e:
        # Any unexpected failure — capture for the meta file
        import traceback

        traceback.print_exc(file=sys.stderr)
        error_msg = f"{type(e).__name__}: {e}"
        exit_code = 1

    # Determine final status
    if processes.is_stop_requested(cu_id):
        status = "stopped"
    elif exit_code == 0:
        status = "succeeded"
    else:
        status = "failed"

    processes.update_meta(
        cu_id,
        status=status,
        exit_code=exit_code,
        finished_at=processes.now_iso(),
        error=error_msg,
    )
    processes.clear_stop(cu_id)
    return exit_code
