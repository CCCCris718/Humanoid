#!/usr/bin/env python3
"""
humanoid-policy-viewer bridge

HTTP http://127.0.0.1:8766
  POST /motion    — push pre-saved .npz (from T2M CLI)
  POST /generate  — text → StableMoFusion → motion (from web UI)

WS   ws://127.0.0.1:8765
  ← web viewer connects here; receives "status" and "motion" messages

Requires: websockets numpy scipy  (pip install websockets numpy scipy)
Optional: pypinyin  (pip install pypinyin) for pinyin sort of Load file list
"""
import asyncio
import io
import json
import logging
import shutil
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation as R

try:
    import websockets
except ImportError:
    raise SystemExit("websockets not found.  pip install websockets")

try:
    from pypinyin import lazy_pinyin
    def _pinyin_key(name: str) -> str:
        return "".join(lazy_pinyin(name, style=0))  # style=0: default, no tone
except ImportError:
    def _pinyin_key(name: str) -> str:
        return name

# ── config ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
WS_HOST   = "127.0.0.1"
WS_PORT   = 8765
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8766

# StableMoFusion server (via SSH tunnel)
SMF_LOCAL_PORT = 17000
SMF_WS_URI = f"ws://127.0.0.1:{SMF_LOCAL_PORT}/ws"

# SSH tunnel: local 17000 → remote REMOTE_PORT on 006 (remote port configurable via /config)
TUNNEL_CONFIG_PATH = _HERE / "data" / "tunnel_config.json"
_default_remote_port = 8000  # robot_38d_225 默认端口


def _load_remote_port() -> int:
    try:
        if TUNNEL_CONFIG_PATH.exists():
            data = json.loads(TUNNEL_CONFIG_PATH.read_text())
            return int(data.get("remote_port", _default_remote_port))
    except Exception:
        pass
    return _default_remote_port


def _save_remote_port(port: int) -> None:
    TUNNEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TUNNEL_CONFIG_PATH.write_text(json.dumps({"remote_port": port}))


_remote_port = _load_remote_port()


def _get_remote_port() -> int:
    return _remote_port


def _set_remote_port(port: int) -> None:
    global _remote_port
    if not (1 <= port <= 65535):
        raise ValueError("remote_port must be 1–65535")
    _remote_port = port
    _save_remote_port(port)
    _stop_tunnel()
    _start_tunnel()


def _ssh_tunnel_cmd() -> list:
    return ["ssh", "-N", "-o", "ExitOnForwardFailure=yes",
            "-L", f"{SMF_LOCAL_PORT}:127.0.0.1:{_remote_port}", "006"]

DATA_DIR = _HERE / "data"  # data/saved, data/generated, data/dataset
GENERATED_DIR = DATA_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
SAVED_DIR = DATA_DIR / "saved"
SAVED_DIR.mkdir(parents=True, exist_ok=True)
DATASET_DIR = DATA_DIR / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="[bridge] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── joint mapping (Isaac → MT / dataset order) ────────────────────────────────
# Matches GMR_view/convert_isaac_to_mt_format_v2.py
ISAAC_JOINT_ORDER = [
    "left_hip_pitch_joint", "right_hip_pitch_joint", "waist_yaw_joint",
    "left_hip_roll_joint",  "right_hip_roll_joint",  "waist_roll_joint",
    "left_hip_yaw_joint",   "right_hip_yaw_joint",   "waist_pitch_joint",
    "left_knee_joint",      "right_knee_joint",
    "left_shoulder_pitch_joint",  "right_shoulder_pitch_joint",
    "left_ankle_pitch_joint",     "right_ankle_pitch_joint",
    "left_shoulder_roll_joint",   "right_shoulder_roll_joint",
    "left_ankle_roll_joint",      "right_ankle_roll_joint",
    "left_shoulder_yaw_joint",    "right_shoulder_yaw_joint",
    "left_elbow_joint",           "right_elbow_joint",
    "left_wrist_roll_joint",      "right_wrist_roll_joint",
    "left_wrist_pitch_joint",     "right_wrist_pitch_joint",
    "left_wrist_yaw_joint",       "right_wrist_yaw_joint",
]
MT_JOINT_ORDER = [
    "left_hip_pitch_joint",  "left_hip_roll_joint",  "left_hip_yaw_joint",
    "left_knee_joint",       "left_ankle_pitch_joint","left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint",  "right_hip_yaw_joint",
    "right_knee_joint",      "right_ankle_pitch_joint","right_ankle_roll_joint",
    "waist_yaw_joint",       "waist_roll_joint",      "waist_pitch_joint",
    "left_shoulder_pitch_joint","left_shoulder_roll_joint","left_shoulder_yaw_joint",
    "left_elbow_joint","left_wrist_roll_joint","left_wrist_pitch_joint","left_wrist_yaw_joint",
    "right_shoulder_pitch_joint","right_shoulder_roll_joint","right_shoulder_yaw_joint",
    "right_elbow_joint","right_wrist_roll_joint","right_wrist_pitch_joint","right_wrist_yaw_joint",
]
_ISAAC_TO_MT = np.array([ISAAC_JOINT_ORDER.index(j) for j in MT_JOINT_ORDER])


# ── shared state ──────────────────────────────────────────────────────────────
_ws_clients: set = set()
_loop: asyncio.AbstractEventLoop | None = None
_generating = False          # simple mutex flag


# ── data conversion ───────────────────────────────────────────────────────────
def _npz_to_standard(data) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, np.ndarray]:
    """Convert npz data (file or dict) to standard (dof_pos, root_pos, root_rot_xyzw, fps, joint_names)."""
    keys = set(data.keys())

    if "dof_pos" in keys:
        dof_pos    = data["dof_pos"].astype(np.float32)
        root_pos   = data["root_pos"].astype(np.float32)
        root_xyzw  = data["root_rot"].astype(np.float32)
        joint_names = data.get("joint_names", np.array(MT_JOINT_ORDER, dtype="<U26"))
    elif "joint_pos" in keys and "body_pos_w" in keys:
        # Isaac Lab format: joint_pos is in Isaac order (interleaved L/R)
        # Reorder to MT order (grouped by body part) per GMR_view convert_isaac_to_mt_format_v2.py
        joint_pos_isaac = data["joint_pos"].astype(np.float32)
        dof_pos         = joint_pos_isaac[:, _ISAAC_TO_MT]
        root_pos        = data["body_pos_w"][:, 0, :].astype(np.float32)
        root_xyzw       = data["body_quat_w"][:, 0, :].astype(np.float32)  # wxyz
        root_xyzw       = np.concatenate([root_xyzw[:, 1:], root_xyzw[:, :1]], axis=-1)  # → xyzw
        joint_names     = np.array(MT_JOINT_ORDER, dtype="<U26")
    elif "joint_pos" in keys and "root_pos" in keys:
        joint_pos_isaac = data["joint_pos"].astype(np.float32)
        root_pos        = data["root_pos"].astype(np.float32)
        root_wxyz       = data["root_rot"].astype(np.float32)
        root_xyzw       = np.concatenate([root_wxyz[:, 1:], root_wxyz[:, :1]], axis=-1)
        dof_pos         = joint_pos_isaac[:, _ISAAC_TO_MT]
        joint_names     = np.array(MT_JOINT_ORDER, dtype="<U26")
    else:
        raise ValueError(f"Unsupported npz format. Got keys: {list(keys)}")

    fps = int(data["fps"].item() if isinstance(data["fps"], np.ndarray) else data["fps"])
    return dof_pos, root_pos, root_xyzw, fps, joint_names


def _npz_bytes_to_clip(data_bytes: bytes) -> tuple[dict, dict]:
    """Convert raw .npz bytes → (deploy_data, web_clip)."""
    data = np.load(io.BytesIO(data_bytes))
    dof_pos, root_pos, root_xyzw, fps, joint_names = _npz_to_standard(data)

    deploy_data = {
        "fps": np.float32(fps),
        "dof_pos": dof_pos,
        "root_pos": root_pos,
        "root_rot": root_xyzw,
        "joint_names": joint_names,
    }
    wxyz = np.concatenate([root_xyzw[:, 3:4], root_xyzw[:, :3]], axis=-1)
    web_clip = {
        "joint_pos": dof_pos.tolist(),
        "root_pos":  root_pos.tolist(),
        "root_quat": wxyz.tolist(),
    }
    return deploy_data, web_clip


def _npz_file_to_clip(path: str) -> dict:
    d = np.load(path, allow_pickle=True)
    dof_pos, root_pos, root_xyzw, _, _ = _npz_to_standard(d)
    wxyz = np.concatenate([root_xyzw[:, 3:4], root_xyzw[:, :3]], axis=-1)
    return {"joint_pos": dof_pos.tolist(), "root_pos": root_pos.tolist(), "root_quat": wxyz.tolist()}


# ── WebSocket broadcast ────────────────────────────────────────────────────────
async def _broadcast(msg: str):
    if not _ws_clients:
        return
    await asyncio.gather(*[c.send(msg) for c in list(_ws_clients)], return_exceptions=True)


def _push_motion_threadsafe(name: str, clip: dict):
    if _loop:
        asyncio.run_coroutine_threadsafe(
            _broadcast(json.dumps({"type": "motion", "name": name, "clip": clip})), _loop
        )


async def _send_status(msg: str, state: str = "info"):
    await _broadcast(json.dumps({"type": "status", "state": state, "message": msg}))


async def _ws_handler(ws):
    _ws_clients.add(ws)
    log.info(f"Viewer connected ({len(_ws_clients)} total)")
    try:
        await ws.wait_closed()
    finally:
        _ws_clients.discard(ws)
        log.info(f"Viewer disconnected ({len(_ws_clients)} remaining)")


# ── generation task ───────────────────────────────────────────────────────────
async def _generate_task(text: str, length: float, steps: int):
    global _generating
    _generating = True
    try:
        await _send_status(f"Generating: '{text}'", "generating")
        log.info(f"Connecting to StableMoFusion: {SMF_WS_URI}")
        try:
            ws = await websockets.connect(SMF_WS_URI, max_size=50 * 1024 * 1024, open_timeout=10)
        except Exception as e:
            await _send_status(f"Failed to connect to StableMoFusion: {e}", "error")
            log.error(f"SMF connect failed: {e}")
            return

        import time
        req = {
            "text": text, "motion_length": length,
            "num_inference_steps": steps,
            "seed": int(time.time()) % 10000,
            "adaptive_smooth": True, "static_start": True,
            "static_frames": 2, "blend_frames": 8,
        }
        await ws.send(json.dumps(req))
        await _send_status("Waiting for server response...", "generating")

        response = await ws.recv()
        await ws.close()

        if isinstance(response, str):
            err = json.loads(response).get("error", response)
            await _send_status(f"Server error: {err}", "error")
            return

        await _send_status("Converting motion data...", "generating")
        deploy_data, web_clip = _npz_bytes_to_clip(response)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = GENERATED_DIR / f"gen_{ts}.npz"
        np.savez(str(save_path), **deploy_data)
        log.info(f"Saved: {save_path}")

        motion_name = f"[T2M] {text}"
        await _broadcast(json.dumps({
            "type": "motion", "name": motion_name,
            "clip": web_clip, "source": save_path.stem,
        }))
        await _send_status(f"Done: '{text}'", "done")
        log.info(f"Pushed motion '{motion_name}'")

    except Exception as e:
        log.error(f"Generation failed: {e}")
        await _send_status(f"Generation failed: {e}", "error")
    finally:
        _generating = False


# ── HTTP handler ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/config":
            body = json.dumps({"remote_port": _get_remote_port()}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/list":
            result = []
            for folder, tag in [(SAVED_DIR, "saved"), (GENERATED_DIR, "generated"), (DATASET_DIR, "dataset")]:
                files = list(folder.glob("*.npz"))
                files.sort(key=lambda f: _pinyin_key(f.stem))
                for f in files:
                    result.append({"name": f.stem, "folder": tag})
            body = json.dumps(result).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._reply(404, b"not found")

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception:
            return self._reply(400, b"invalid json")

        if self.path == "/load":
            name   = body.get("name", "").strip()
            folder = body.get("folder", "generated")
            if not name:
                return self._reply(400, b"name required")
            _folder_map = {"saved": SAVED_DIR, "generated": GENERATED_DIR, "dataset": DATASET_DIR}
            base = _folder_map.get(folder, GENERATED_DIR)
            path = base / f"{name}.npz"
            if not path.exists():
                return self._reply(404, f"not found: {name}".encode())
            try:
                clip = _npz_file_to_clip(str(path))
            except Exception as e:
                return self._reply(500, str(e).encode())
            _push_motion_threadsafe(f"[LOAD] {name}", clip)
            log.info(f"Loaded '{folder}/{name}' via /load")
            self._reply(200, b"ok")

        elif self.path == "/motion":
            name = body.get("name", "generated")
            if "path" in body:
                try:
                    clip = _npz_file_to_clip(body["path"])
                except Exception as e:
                    return self._reply(500, str(e).encode())
            elif "clip" in body:
                clip = body["clip"]
            else:
                return self._reply(400, b"need 'path' or 'clip'")
            _push_motion_threadsafe(name, clip)
            self._reply(200, b"ok")

        elif self.path == "/save":
            name      = body.get("name", "").strip().rstrip(".").strip()
            source    = body.get("source", "").strip()
            overwrite = bool(body.get("overwrite", False))
            if not name or not source:
                return self._reply(400, b"need 'name' and 'source'")
            src_path  = GENERATED_DIR / f"{source}.npz"
            if not src_path.exists():
                return self._reply(404, f"source not found: {source}".encode())
            # sanitize filename
            safe_name = "".join(c for c in name if c not in r'\/:*?"<>|').strip()
            if not safe_name:
                return self._reply(400, b"invalid name")
            dst_path = SAVED_DIR / f"{safe_name}.npz"
            if dst_path.exists() and not overwrite:
                return self._reply(409, b"exists")
            shutil.copy2(src_path, dst_path)
            log.info(f"Saved '{safe_name}.npz' to data/saved/")
            self._reply(200, json.dumps({"saved": safe_name}).encode())

        elif self.path == "/clear":
            files = list(GENERATED_DIR.glob("gen_*.npz"))
            for f in files:
                try:
                    f.unlink()
                except Exception:
                    pass
            log.info(f"Cleared {len(files)} gen_*.npz files")
            self._reply(200, json.dumps({"deleted": len(files)}).encode())

        elif self.path == "/generate":
            if _generating:
                return self._reply(409, b"already generating")
            text   = body.get("text", "").strip()
            length = float(body.get("length", 4.0))
            steps  = int(body.get("steps", 10))
            if not text:
                return self._reply(400, b"text required")
            asyncio.run_coroutine_threadsafe(_generate_task(text, length, steps), _loop)
            self._reply(202, b"accepted")

        elif self.path == "/config":
            port = body.get("remote_port")
            if port is None:
                return self._reply(400, b"remote_port required")
            try:
                port = int(port)
            except (TypeError, ValueError):
                return self._reply(400, b"remote_port must be integer")
            try:
                _set_remote_port(port)
            except ValueError as e:
                return self._reply(400, str(e).encode())
            self._reply(200, json.dumps({"remote_port": _get_remote_port()}).encode())

        else:
            self._reply(404, b"not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _reply(self, code: int, body: bytes):
        self.send_response(code)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def log_message(self, *_):
        pass


def _run_http():
    srv = HTTPServer((HTTP_HOST, HTTP_PORT), _Handler)
    log.info(f"HTTP  http://{HTTP_HOST}:{HTTP_PORT}  (/motion  /generate)")
    srv.serve_forever()


# ── SSH tunnel manager ────────────────────────────────────────────────────────
_tunnel_proc: subprocess.Popen | None = None
_tunnel_lock = threading.Lock()


def _start_tunnel() -> bool:
    global _tunnel_proc
    with _tunnel_lock:
        if _tunnel_proc and _tunnel_proc.poll() is None:
            return True  # already running
        cmd = _ssh_tunnel_cmd()
        log.info(f"SSH tunnel: {' '.join(cmd)}")
        try:
            _tunnel_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)  # give ssh time to bind the port
            if _tunnel_proc.poll() is not None:
                log.error("SSH tunnel exited immediately — check ssh alias and key")
                return False
            log.info("SSH tunnel started")
            return True
        except FileNotFoundError:
            log.error("ssh not found in PATH")
            return False


def _stop_tunnel():
    global _tunnel_proc
    with _tunnel_lock:
        if _tunnel_proc and _tunnel_proc.poll() is None:
            _tunnel_proc.terminate()
            _tunnel_proc = None
            log.info("SSH tunnel stopped")


def _tunnel_watchdog():
    """Restart tunnel if it dies unexpectedly."""
    while True:
        time.sleep(5)
        with _tunnel_lock:
            dead = _tunnel_proc is None or _tunnel_proc.poll() is not None
        if dead:
            log.warning("SSH tunnel down — restarting...")
            _start_tunnel()


# ── main ──────────────────────────────────────────────────────────────────────
async def main():
    global _loop
    _loop = asyncio.get_running_loop()

    # Start SSH tunnel
    _start_tunnel()
    threading.Thread(target=_tunnel_watchdog, daemon=True).start()

    threading.Thread(target=_run_http, daemon=True).start()
    try:
        async with websockets.serve(_ws_handler, WS_HOST, WS_PORT):
            log.info(f"WS    ws://{WS_HOST}:{WS_PORT}")
            log.info("Ready.")
            await asyncio.Future()
    finally:
        _stop_tunnel()


if __name__ == "__main__":
    asyncio.run(main())
