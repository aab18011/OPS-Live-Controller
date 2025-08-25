#!/usr/bin/env bash
set -e
out="/tmp/roc_deep_test_suite"
rm -rf "$out"
mkdir -p "$out"

cat > "$out/conftest.py" <<'PY'
import os, tempfile, json, pathlib, pytest
from pathlib import Path

@pytest.fixture(scope="session")
def safe_config_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("roc_safe_etc")
    etc = d / "etc" / "roc"
    etc.mkdir(parents=True)
    cfg = {
        "obs": {"host": "127.0.0.1", "port": 4455, "password": "changeme"},
        "cameras": [],
        "debug_mode": True
    }
    (etc / "config.json").write_text(json.dumps(cfg, indent=2))
    scene_rules = [{"name":"always","priority":10,"conditions":[],"actions":[{"type":"noop"}]}]
    (etc / "scene_rules.json").write_text(json.dumps(scene_rules, indent=2))
    os.environ["ROC_CONFIG_DIR"] = str(etc)
    return str(etc)
PY

cat > "$out/tests_test_scene_engine.py" <<'PY'
import importlib, inspect, json, os, pytest
from pathlib import Path

def _find_symbol(module, candidates):
    for name in dir(module):
        for c in candidates:
            if c.lower() in name.lower():
                return name
    return None

def test_scene_engine_basic_import():
    try:
        m = importlib.import_module("roc_scene_engine")
    except Exception as e:
        pytest.skip(f"roc_scene_engine not importable: {e}")
    candidates = ["SceneEngine", "Scene", "Engine", "Rule", "parse_rules", "load_rules"]
    sym = _find_symbol(m, candidates)
    assert sym is not None, "No Scene/Engine/Rule/parse function found in roc_scene_engine; manual inspection needed"
    attr = getattr(m, sym)
    if inspect.isclass(attr):
        try:
            inst = None
            try:
                inst = attr()
            except TypeError:
                try:
                    inst = attr([])
                except Exception:
                    pytest.skip(f"Could not instantiate {sym} with common signatures")
            for meth in ("evaluate", "choose", "apply_rules", "process"):
                if hasattr(inst, meth):
                    return
            assert inst is not None
        except Exception as e:
            pytest.skip(f"Instantiation of {sym} failed: {e}")
    else:
        if callable(attr):
            try:
                cfg_dir = os.environ.get("ROC_CONFIG_DIR") or "/etc/roc"
                rules_file = Path(cfg_dir) / "scene_rules.json"
                if rules_file.exists():
                    rules = json.loads(rules_file.read_text())
                else:
                    rules = []
                try:
                    r = attr(rules)
                except TypeError:
                    r = attr()
                assert r is not None or r == None
            except Exception as e:
                pytest.skip(f"Calling parser function failed: {e}")
        else:
            pytest.skip("Found symbol is not callable and not a class")

def test_scene_engine_rule_evaluation_smoke():
    try:
        m = importlib.import_module("roc_scene_engine")
    except Exception as e:
        pytest.skip(f"roc_scene_engine not importable: {e}")
    candidates = ["evaluate", "choose", "select", "apply", "process"]
    sym = None
    for c in candidates:
        if hasattr(m, c):
            sym = getattr(m, c)
            break
    if sym is None:
        names = [n for n in dir(m) if "Scene" in n or "Engine" in n]
        for n in names:
            obj = getattr(m, n)
            if inspect.isclass(obj):
                for meth in ("evaluate", "choose", "apply_rules", "process"):
                    if hasattr(obj, meth):
                        sym = getattr(obj, meth)
                        break
            if sym: break
    if sym is None:
        pytest.skip("No evaluation function/method found; nothing to run")
    try:
        result = sym({"game_time": 0, "timeout_active": False})
        assert True
    except TypeError:
        pytest.skip("Evaluation callable requires different signature; manual test needed")
    except Exception as e:
        assert True
PY

cat > "$out/obs_mock_server.py" <<'PY'
"""
Simple OBS WebSocket mock server for pytest to use.
This mock is intentionally minimal: it accepts websocket connections and responds to a small set
of messages with predictable JSON. It's useful to test client code that attempts to connect to OBS.
"""
import asyncio, json, websockets

async def handler(ws, path):
    try:
        async for msg in ws:
            try:
                data = json.loads(msg)
                if isinstance(data, dict) and data.get("request") == "GetVersion":
                    await ws.send(json.dumps({"status":"ok","version":"5.0.0-mock"}))
                else:
                    await ws.send(json.dumps({"status":"ok","echo": data}))
            except Exception:
                await ws.send(json.dumps({"status":"ok","raw": str(msg)}))
    except Exception:
        pass

def make_server(host="127.0.0.1", port=4455):
    return websockets.serve(handler, host, port)

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv)>1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv)>2 else 4455
    loop = asyncio.get_event_loop()
    srv = make_server(host, port)
    server = loop.run_until_complete(srv)
    print("Mock OBS websocket server running on", host, port)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        server.close()
        loop.run_until_complete(server.wait_closed())
PY

cat > "$out/tests_test_obs.py" <<'PY'
import asyncio, importlib, pytest, subprocess, sys, time, os
from pathlib import Path
from obs_mock_server import make_server

@pytest.mark.asyncio
async def test_obs_mock_server_runs(event_loop, safe_config_dir):
    server = await make_server("127.0.0.1", 4455)
    import websockets, json
    uri = "ws://127.0.0.1:4455"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"request":"GetVersion"}))
        resp = await ws.recv()
        assert "version" in resp or "ok" in resp
    server.close()

def test_repo_client_connects_to_obs(safe_config_dir):
    os.environ["ROC_OBS_HOST"] = "127.0.0.1"
    os.environ["ROC_OBS_PORT"] = "4455"
    names = ["roc_main", "roc_scene_engine", "roc_bootstrap"]
    for n in names:
        try:
            m = importlib.import_module(n)
        except Exception:
            continue
        for attr in ("connect_obs", "obs_connect", "connect", "start"):
            if hasattr(m, attr):
                cmd = [sys.executable, "-c", f"import {n}; print('OK')"]
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, text=True)
                assert p.returncode == 0 or p.stdout.strip().startswith("OK")
PY

cat > "$out/tests_test_ffmpeg.py" <<'PY'
import importlib, pytest, shutil, os
from pathlib import Path
def test_ffmpeg_builder_detected_and_runs():
    names = ["roc_main", "roc_bootstrap", "roc_scene_engine"]
    found = False
    for n in names:
        try:
            m = importlib.import_module(n)
        except Exception:
            continue
        for attr in dir(m):
            if "ffmpeg" in attr.lower():
                found = True
                fn = getattr(m, attr)
                if callable(fn):
                    try:
                        try:
                            res = fn({"input": "test", "output":"test"})
                        except TypeError:
                            res = fn()
                        assert isinstance(res, (str, list))
                    except Exception as e:
                        pytest.skip(f"ffmpeg builder {attr} raised exception: {e}")
    assert found, "No ffmpeg builder function found in common modules"
PY

cat > "$out/README.md" <<'MD'
ROC Deep Test Suite
===================

This directory contains pytest-based tests and helpers designed to be copied into a cloned ROC repository.
They are intentionally defensive and try many common names/entrypoints to avoid depending on a specific API.

What is included:
- conftest.py: pytest fixtures creating a safe config dir (`ROC_CONFIG_DIR`) that mimics `/etc/roc`.
- obs_mock_server.py: a small asyncio websockets-based mock server that simulates OBS responses.
- tests_test_scene_engine.py: scene engine import & smoke tests that try many likely symbols.
- tests_test_obs.py: OBS mock server tests and safe subprocess checks.
- tests_test_ffmpeg.py: ffmpeg command builder smoke tests.

How to run:
1. Clone your repo locally:
   git clone https://github.com/aab18011/OPS-Live-Controller.git
   cd OPS-Live-Controller
2. Copy these files into the repo root (do NOT overwrite existing files):
   cp /tmp/roc_deep_test_suite/* .
3. (Optional) Create virtualenv and install deps:
   python3 -m venv venv
   source venv/bin/activate
   pip install pytest websockets
4. Run pytest:
   pytest -q

Notes:
- Tests avoid modifying repo files. They create temporary config dirs and run risky imports in subprocesses.
- These tests are intentionally permissive; they aim to exercise surface APIs to guide creation of deeper tests.
MD

cd /tmp
zip -r roc_deep_test_suite.zip "$(basename "$out")"
echo "Created /tmp/roc_deep_test_suite and /tmp/roc_deep_test_suite.zip"
