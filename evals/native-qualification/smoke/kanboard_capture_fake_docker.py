#!/usr/bin/env python3
"""Provider-free Docker CLI stand-in for the preactivation abort E2E only."""

import json
from pathlib import Path
import sys


path = Path(__file__).with_name("fake-docker-state.json")
state = json.loads(path.read_text())
args = sys.argv[1:]
network_id = "b" * 64


def save():
    path.write_text(json.dumps(state, sort_keys=True))


def out(value):
    print(value)
    save()
    sys.exit(0)


if state.get("mode") == "freeze":
    if args[:2] == ["container", "inspect"] and args[2] in state["containers"]:
        out(json.dumps([state["containers"][args[2]]]))
    if args[:2] == ["container", "stop"] and args[-1] == state["collector_id"]:
        collector = state["containers"][state["collector_id"]]
        collector["State"] = {"Status": "exited", "Running": False, "Paused": False}
        state["stop_calls"] = state.get("stop_calls", 0) + 1
        out(state["collector_id"])
    sys.exit(2)

if args[:2] == ["container", "inspect"] and args[2] == state["app"]["Id"]:
    out(json.dumps([state["app"]]))
if args[:2] == ["network", "create"]:
    state["network"] = {
        "Id": network_id, "Name": args[-1], "Internal": True,
        "Labels": {"io.lrh.kanboard-capture": args[args.index("--label") + 1].split("=", 1)[1]},
        "IPAM": {"Config": [{"Subnet": "172.30.0.0/24", "Gateway": "172.30.0.1"}]},
        "Containers": {},
    }
    out(network_id)
if args[:2] == ["network", "inspect"] and state.get("network") and args[2] == network_id:
    out(json.dumps([state["network"]]))
if args[:2] == ["network", "connect"]:
    ip = args[args.index("--ip") + 1]
    state["app"]["NetworkSettings"]["Networks"][state["network"]["Name"]] = {
        "IPAddress": "", "IPAMConfig": {"IPv4Address": ip}}
    state["network"]["Containers"][state["app"]["Id"]] = {}
    out("")
if args[:2] == ["container", "create"]:
    state["injected_collector_create_failure"] = True
    save()
    sys.exit(1)
if args[:2] == ["container", "ls"]:
    out("")
if args[:2] == ["network", "ls"]:
    out(network_id if state.get("network") else "")
if args[:2] == ["network", "disconnect"] and state.get("network"):
    state["app"]["NetworkSettings"]["Networks"].pop(state["network"]["Name"], None)
    state["network"]["Containers"].pop(state["app"]["Id"], None)
    out("")
if args[:2] == ["network", "rm"] and state.get("network") and args[2] == network_id:
    if state["network"]["Containers"]:
        sys.exit(1)
    state["network"] = None
    out(network_id)
sys.exit(2)
