"""The steps of `python solms.py`, each importing only what it needs."""

from __future__ import annotations

import json
import socket
import struct

from . import frame as F

SKIN = {1: "marble"}


def _qgis_exec(code: str, timeout: float = 1800):
    """Run Python in the open QGIS through its MCP plug-in's socket; None if QGIS is not listening."""
    try:
        s = socket.create_connection(("127.0.0.1", 9876), timeout=2)
    except OSError:
        return None
    with s:
        s.settimeout(timeout)
        body = json.dumps({"type": "execute_code", "params": {"code": code, "timeout": int(timeout)}}).encode()
        s.sendall(struct.pack(">I", len(body)) + body)
        n = struct.unpack(">I", _recv(s, 4))[0]
        return json.loads(_recv(s, n))


def _recv(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("QGIS closed the connection")
        buf += chunk
    return buf


def ground(args):
    name = f"phase{args.phase}"
    code = f"""
import sys, importlib
V = {str(F.VIDEO.as_posix())!r}
if V + "/solms" not in sys.path:
    sys.path.insert(0, V + "/solms")
import cgsolms.frame as F
importlib.reload(F)
exec(open(V + "/solms/cgsolms/qgis_ground.py", encoding="utf8").read())
solms_ground(F.frame({name!r}), str(F.ground_dir({name!r})), redo={bool(args.redo)!r}, show=True)
"""
    reply = _qgis_exec(code)
    if reply is None:
        raise SystemExit("QGIS is not listening: open QGIS and start its MCP server (the plug-in's toolbar button)")
    res = reply.get("result", reply)
    print(res.get("stdout", "") or res)
    from . import ground as gr
    gr.build_plate(name, SKIN[args.phase], gimp=not args.no_gimp)


def run(args):
    if args.step in ("ground", "all"):
        ground(args)
    if args.step in ("cast", "all"):
        from . import cast
        cast.build(args.phase)
    if args.step in ("compose", "all"):
        from . import compose
        compose.build(args.phase)
    if args.step == "stills":
        from . import render
        render.stills(args.phase, args.times)
    if args.step in ("blender", "all"):
        from . import blender
        blender.build(args.phase)
    if args.step in ("score", "all"):
        from . import score
        score.build(args.phase)
    if args.step in ("render", "all"):
        from . import render
        render.render(args.phase, workers=args.workers, quality=args.quality, t0=args.t0, t1=args.t1)
    if args.step in ("resolve", "all"):
        from . import resolve
        resolve.build(args.phase)
    if args.step in ("thumbnail", "all"):
        from . import thumbnail
        thumbnail.build(args.phase)
    if args.step in ("publish", "all"):
        from . import publish
        publish.build(args.phase)
