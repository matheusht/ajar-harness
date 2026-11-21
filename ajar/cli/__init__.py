"""Command-line interface for Ajar (`ajar` CLI).

Provides one deterministic interface across Host Mode (Codex, Antigravity,
Claude Code, OMP) and Standalone Product Mode (`ajar run`).
"""

from __future__ import annotations

import json
import sys
from typing import Sequence

from ajar.cli.claims import (
    cmd_chain as cmd_chain,
)
from ajar.cli.claims import (
    cmd_claim as cmd_claim,
)
from ajar.cli.claims import (
    cmd_finding as cmd_finding,
)
from ajar.cli.claims import (
    cmd_patch as cmd_patch,
)
from ajar.cli.claims import (
    cmd_repro as cmd_repro,
)
from ajar.cli.common import (
    _check_sqlite_fts5 as _check_sqlite_fts5,
)
from ajar.cli.common import (
    _emit as _emit,
)
from ajar.cli.hunt import (
    cmd_anomaly as cmd_anomaly,
)
from ajar.cli.hunt import (
    cmd_binding as cmd_binding,
)
from ajar.cli.hunt import (
    cmd_coverage as cmd_coverage,
)
from ajar.cli.hunt import (
    cmd_door as cmd_door,
)
from ajar.cli.hunt import (
    cmd_driver as cmd_driver,
)
from ajar.cli.hunt import (
    cmd_primitive as cmd_primitive,
)
from ajar.cli.hunt import (
    cmd_surface as cmd_surface,
)
from ajar.cli.hunt import (
    cmd_task as cmd_task,
)
from ajar.cli.ops import (
    cmd_brief as cmd_brief,
)
from ajar.cli.ops import (
    cmd_context as cmd_context,
)
from ajar.cli.ops import (
    cmd_doctor as cmd_doctor,
)
from ajar.cli.ops import (
    cmd_economics as cmd_economics,
)
from ajar.cli.ops import (
    cmd_epistemic_hooks as cmd_epistemic_hooks,
)
from ajar.cli.ops import (
    cmd_export_graph as cmd_export_graph,
)
from ajar.cli.ops import (
    cmd_finish as cmd_finish,
)
from ajar.cli.ops import (
    cmd_gate_check as cmd_gate_check,
)
from ajar.cli.ops import (
    cmd_hook as cmd_hook,
)
from ajar.cli.ops import (
    cmd_init as cmd_init,
)
from ajar.cli.ops import (
    cmd_ledger as cmd_ledger,
)
from ajar.cli.ops import (
    cmd_loop as cmd_loop,
)
from ajar.cli.ops import (
    cmd_map as cmd_map,
)
from ajar.cli.ops import (
    cmd_phase as cmd_phase,
)
from ajar.cli.ops import (
    cmd_pulse as cmd_pulse,
)
from ajar.cli.ops import (
    cmd_quote as cmd_quote,
)
from ajar.cli.ops import (
    cmd_ref_query as cmd_ref_query,
)
from ajar.cli.ops import (
    cmd_reopen as cmd_reopen,
)
from ajar.cli.ops import (
    cmd_report as cmd_report,
)
from ajar.cli.ops import (
    cmd_run as cmd_run,
)
from ajar.cli.ops import (
    cmd_spend as cmd_spend,
)
from ajar.cli.ops import (
    cmd_status as cmd_status,
)
from ajar.cli.ops import (
    cmd_steer as cmd_steer,
)
from ajar.cli.ops import (
    cmd_swarm as cmd_swarm,
)
from ajar.cli.ops import (
    cmd_threat_model as cmd_threat_model,
)
from ajar.cli.ops import (
    cmd_touch as cmd_touch,
)
from ajar.cli.parser import (
    _get_cached_parser as _get_cached_parser,
)
from ajar.cli.parser import (
    build_parser as build_parser,
)
from ajar.db import AjarError
from ajar.domain import InvalidTransitionError
from ajar.redact import scrub_text


def main(argv: Sequence[str] | None = None) -> int:
    parser = _get_cached_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (AjarError, InvalidTransitionError) as exc:
        err_obj = {"error": scrub_text(str(exc)), "exit_code": exc.exit_code, **exc.details}
        sys.stderr.write(json.dumps(err_obj, sort_keys=True) + "\n")
        return int(exc.exit_code)
    except KeyboardInterrupt:
        return 130
