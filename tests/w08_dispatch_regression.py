#!/usr/bin/env python3
"""W08 function-level regression; never import or launch the installed product.

Use only in an authorized offhost test workspace. AST selection is NOT a sandbox
for malicious Python. Inputs must be reviewed and bound to the required hashes.
--input-kind excerpt explicitly means a retrieved/manual source reproduction,
not verification or execution of the full original module. Even full-module
inputs run ONLY the selected functions with synthetic ports, not product E2E.
"""
import argparse
import ast
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
from subprocess import TimeoutExpired
import sys
from threading import Lock
from time import monotonic
from types import SimpleNamespace

MAX_INPUT = 1024 * 1024
FLOW_NAMES = {
    'FlowError', 'UnknownOutcome', '_need', '_json', '_object',
    'SessionObservation', 'RunRecord', 'CodexAdapter',
}


def selected_nodes(path, digest, names):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular input required')
    if path.stat().st_size > MAX_INPUT:
        raise ValueError('input size exceeded')
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != digest:
        raise ValueError('input SHA256 mismatch: ' + path.name)
    tree = ast.parse(data, filename=path.name)
    found = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    if len(found) != len(names) or {n.name for n in found} != names:
        raise ValueError('missing or duplicate selected definition')
    for node in found:
        if isinstance(node, ast.ClassDef) and node.name == 'CodexAdapter':
            node.body = [n for n in node.body if isinstance(n, ast.FunctionDef)
                         and n.name in {'__init__', 'run', 'cancel_owned'}]
            if {n.name for n in node.body} != {'__init__', 'run', 'cancel_owned'}:
                raise ValueError('unexpected adapter structure')
    module = ast.Module(body=found, type_ignores=[])
    return ast.fix_missing_locations(module), actual


def run_case(dispatch_tree, flow_tree, scenario):
    events, records = [], []
    ns = {'__name__': 'w08_review_only', 'dataclass': dataclass, 'asdict': asdict,
          'json': json, 'Lock': Lock, 'datetime': datetime, 'timedelta': timedelta,
          'timezone': timezone, 'monotonic': monotonic, 'isfinite': isfinite,
          'TimeoutExpired': TimeoutExpired, '_MAX_MESSAGE': MAX_INPUT,
          'BUILDER': 'cherub_builder'}
    exec(compile(flow_tree, '<reviewed-flow-functions>', 'exec'), ns)
    adapter_class = ns['CodexAdapter']

    class ObservedAdapter(adapter_class):
        def run(self, *args, **kwargs):
            record = super().run(*args, **kwargs)
            records.append(record)
            return record

    flow = SimpleNamespace(**{key: value for key, value in ns.items() if key != '__builtins__'})
    instances = []

    def make_adapter():
        adapter = ObservedAdapter()
        instances.append(adapter)
        return adapter
    flow.CodexAdapter = make_adapter
    deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
    document = {'scope': {'files': ['module.py'], 'operations': ['execute']},
                'budget': {'deadline': deadline.strftime('%Y-%m-%dT%H:%M:%SZ')},
                'input': {'sha256': 'a' * 64}}
    if scenario == 'no_execute_scope':
        document['scope']['operations'] = []
    contracts = SimpleNamespace(ContractError=ValueError,
        validate_for_dispatch=lambda value, policy: SimpleNamespace(to_dict=lambda: deepcopy(value)))

    def bind(*args):
        events.append('bind')
        return {'sha256': 'b' * 64}
    def verify(*args):
        events.append('verify')
    candidates = SimpleNamespace(CandidateError=ValueError,
        verify_source_binding=lambda *args: {'source_files':
            ['foreign.py'] if scenario == 'source_outside_scope' else ['module.py']},
        bind_candidate=bind, verify_candidate=verify)

    class Registry:
        def deliver(self, envelope, identity, *, contract, policy, execute):
            events.append('registry')
            if scenario == 'registry_denied':
                raise flow.FlowError('synthetic registry denial')
            return execute({}, contract)

    class Child:
        pid = 12345  # Synthetic identifier only; no OS process is created.
        def wait(self, timeout):
            events.append('wait')
            if scenario == 'wait_error':
                raise RuntimeError('synthetic wait error')
            if scenario == 'cancelled':
                instances[-1]._cancelled = True
            return 13 if scenario == 'exit_nonzero' else 0
        def terminate(self):
            events.append('terminate')
        def kill(self):
            events.append('kill')

    def gate(*args):
        events.append('gate')
        if scenario == 'gate_exception':
            raise RuntimeError('synthetic gate exception')
        return scenario != 'gate_denied'

    def factory(*args):
        events.append('factory')
        if scenario == 'noncallable_factory':
            return None
        def start(*args):
            events.append('start')
            model = None if scenario == 'model_missing' else (
                'other-model' if scenario == 'model_mismatch' else 'synthetic-model')
            final = None if scenario == 'final_missing' else {'synthetic': True}
            return flow.SessionObservation(Child(), final,
                scenario != 'stream_incomplete', model, scenario == 'model_error')
        return start

    def collect():
        events.append('collect')
        return {'synthetic': True}

    modules = {'cherub_flow': flow, 'cherub_candidate': candidates,
               'cherub_task_contract': contracts}
    scope = {'_z1_module': modules.__getitem__}
    exec(compile(dispatch_tree, '<reviewed-dispatch-function>', 'exec'), scope)
    policy = SimpleNamespace(source_root='synthetic', candidate_root='synthetic',
        deadline=deadline, model_requested='synthetic-model', model_reasoning_effort='synthetic')
    error = None
    error_record = None
    try:
        scope['dispatch_task'](document, {}, None, policy=policy, registry=Registry(),
            cli_version='synthetic', session_id='synthetic', start_factory=factory,
            execution_gate=gate, collect_candidate=collect)
    except Exception as exc:
        error = type(exc).__name__
        error_record = getattr(exc, 'record', None)

    no_effect = {'gate_denied', 'gate_exception', 'no_execute_scope',
                 'source_outside_scope', 'registry_denied'}
    if scenario == 'complete':
        ok = (error is None and records and records[-1].status == 'COMPLETE'
              and events == ['registry', 'gate', 'factory', 'start', 'wait', 'collect', 'bind', 'verify'])
    elif scenario in no_effect:
        ok = (error is not None and not any(x in events for x in ('factory', 'start', 'collect', 'bind', 'verify')))
    else:
        ok = (error is not None and not any(x in events for x in ('collect', 'bind', 'verify'))
              and (not records or error_record is records[-1]))
    return {'case': scenario, 'verdict': 'PASS' if ok else 'FAIL',
            'events': events, 'adapter_status': records[-1].status if records else None,
            'exception': error,
            'error_record_status': getattr(error_record, 'status', None)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--agentctl', required=True, type=Path)
    ap.add_argument('--flow', required=True, type=Path)
    ap.add_argument('--agentctl-sha256', required=True)
    ap.add_argument('--flow-sha256', required=True)
    ap.add_argument('--input-kind', choices=('full-module', 'excerpt'), required=True)
    opts = ap.parse_args()
    try:
        dispatch_tree, adigest = selected_nodes(opts.agentctl, opts.agentctl_sha256, {'dispatch_task'})
        flow_tree, fdigest = selected_nodes(opts.flow, opts.flow_sha256, FLOW_NAMES)
        scenarios = ('complete', 'gate_denied', 'gate_exception', 'stream_incomplete',
            'final_missing', 'exit_nonzero', 'model_error', 'model_missing', 'model_mismatch',
            'cancelled', 'wait_error', 'no_execute_scope', 'source_outside_scope',
            'registry_denied', 'noncallable_factory')
        rows = [run_case(dispatch_tree, flow_tree, case) for case in scenarios]
        report = {'schema': 'eta-w08-function-regression/1', 'input_kind': opts.input_kind,
            'agentctl_input_sha256': adigest, 'flow_input_sha256': fdigest,
            'test_scope': 'SELECTED_FUNCTIONS_SYNTHETIC_PORTS',
            'real_processes_created': 0, 'real_ledger_opened': False,
            'total': len(rows), 'passed': sum(row['verdict'] == 'PASS' for row in rows),
            'cases': rows, 'native_product': 'NOT_TESTED', 'admission': 'NOT_GRANTED'}
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
        return 0 if report['passed'] == report['total'] else 1
    except (ValueError, OSError, SyntaxError) as exc:
        print(json.dumps({'result': 'BLOCKED', 'reason': str(exc)}))
        return 20


if __name__ == '__main__':
    raise SystemExit(main())
