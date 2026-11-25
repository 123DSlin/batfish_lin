"""Independent iBDP validation helpers for the BGP single-path region contract.

Concrete forwarding is read from fresh RIB exports, not derived from the SMT
model. Ambiguous routes, incomplete fault coverage and malformed snapshots are
rejected instead of being interpreted as successful delivery.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import ipaddress
from itertools import combinations
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


class ValidationError(RuntimeError):
    """An independent validation could not establish its declared coverage."""


@dataclass(frozen=True)
class Route:
    peer: str | None
    protocol: str
    interface: str
    prefix: str


@dataclass(frozen=True)
class ConcreteScenario:
    failed_links: frozenset[str]
    routes: dict[str, Route]
    source: Path


def configuration_hashes(configs: Path) -> dict[str, str]:
    files = sorted(configs.glob('*.cfg'))
    if not files:
        raise ValidationError(f'no configuration files: {configs}')
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in files}


def prepare_prepend_snapshot(configs: Path, snapshot: Path, router: str, policy: str,
                             sequence: int, asn: int, cost: int) -> dict[str, str]:
    """Edit exactly one known route-map stanza in a disposable configuration copy.

    A zero effective cost omits the command. The original stanza is required
    to contain exactly one copy of the expected ASN, matching the reference pin.
    """
    if not 0 <= cost <= 65534 or not 1 <= asn <= 4294967295:
        raise ValueError('invalid prepend cost or ASN')
    files = [p for p in configs.glob('*.cfg') if re.search(
        rf'^hostname\s+{re.escape(router)}\s*$', p.read_text(), re.M | re.I)]
    if len(files) != 1:
        raise ValidationError(f'expected one configuration for router {router}')
    source = files[0]
    text = source.read_text()
    pattern = re.compile(rf'(?m)^route-map {re.escape(policy)} permit {sequence}\s*\n'
                         r'(?P<body>(?:[ \t]+[^\n]*\n)*)')
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValidationError('expected exactly one target route-map stanza')
    match = matches[0]
    body = match.group('body')
    command = f' set as-path prepend {asn}\n'
    if body.count(command) != 1 or len(re.findall(r'^\s+set as-path prepend\b', body, re.M)) != 1:
        raise ValidationError('reference prepend does not match the modeled one-AS statement')
    replacement = ' set as-path prepend' + f' {asn}' * cost + '\n' if cost else ''
    rewritten = text[:match.start('body')] + body.replace(command, replacement) + text[match.end('body'):]
    shutil.copytree(configs, snapshot/'configs')
    (snapshot/'configs'/source.name).write_text(rewritten)
    return configuration_hashes(snapshot/'configs')


def run_batfish(snapshot: Path, output: Path, launcher: Path, *, ingress: str,
                destination: str, k: int, timeout: float, symbolic: bool = False,
                final_nodes: str = '.*', java_binary: Path | None = None) -> Path:
    """Run a bounded local launcher and kill its process group on timeout."""
    if not launcher.is_file() or timeout <= 0:
        raise ValidationError('missing launcher or invalid timeout')
    output.mkdir(parents=True, exist_ok=False)
    output, snapshot, launcher = output.resolve(), snapshot.resolve(), launcher.resolve()
    method = 'testReachability' if symbolic else 'testFailureDataplaneEnumeration'
    library = os.environ.get('BATFISH_Z3_JAVA_LIBRARY', str(Path.home()/'Library/Java/Extensions'))
    environment = dict(os.environ)
    if java_binary is not None:
        if not java_binary.is_file():
            raise ValidationError(f'missing Java executable: {java_binary}')
        environment['JAVABIN'] = str(java_binary.resolve())
    environment.update(
        SMT_CONFIG_DIRECTORY=str(snapshot), SMT_DIRECTORY_PREFIX=str(output),
        SMT_SYMBOLIC='false', SMT_PROTOCOLS='BGP', SMT_SKIP_SYMBOLIC_ROUTES='false',
        SMT_INGRESS=ingress, SMT_FINAL=final_nodes, SMT_DST=destination, SMT_FAILURES=str(k),
        SMT_ENUMERATE_FAILURES=str(not symbolic).lower(), FAIL_K=str(k), FAIL_MODE='AT_MOST_K',
        TMPDIR=str(output), TEST_TMPDIR=str(output), RUNFILES_DIR=str(launcher)+'.runfiles',
        TESTBRIDGE_TEST_ONLY=f'org.batfish.minesweeper.smt.SmtReachabilityTest#{method}',
        JAVA_TOOL_OPTIONS=(os.environ.get('JAVA_TOOL_OPTIONS', '') +
                           ' --add-opens=java.base/java.lang=ALL-UNNAMED' +
                           f' -Djava.library.path={library} -Djava.io.tmpdir={output}').strip())
    started = time.monotonic()
    with (output/'run.log').open('w') as log:
        process = subprocess.Popen([str(launcher)], env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ValidationError(f'Batfish timed out; see {output}/run.log') from exc
    (output/'execution.json').write_text(json.dumps(dict(
        launcher=str(launcher), launcher_sha256=sha256(launcher.read_bytes()).hexdigest(),
        java_binary=environment.get('JAVABIN', 'launcher-default'),
        method=method, exit_code=code, seconds=time.monotonic()-started,
        configuration_sha256=configuration_hashes(snapshot/'configs')), indent=2)+'\n')
    if code:
        raise ValidationError(f'Batfish exited {code}; see {output}/run.log')
    if symbolic:
        exports = list(output.glob('smt_output_*/smt_encoding.smt2'))
        if len(exports) != 1:
            raise ValidationError('symbolic launcher omitted a unique encoding')
        return exports[0].parent
    exports = list(output.glob(f'smt_output_*/failure_enumeration/failures_AT_MOST_K_k{k}'))
    if len(exports) != 1:
        raise ValidationError('concrete launcher omitted a unique failure export')
    return exports[0]


def read_concrete_scenarios(directory: Path, routers: set[str], physical_links: set[str],
                            destination: str, k: int) -> dict[frozenset[str], ConcreteScenario]:
    address = ipaddress.IPv4Network(destination).network_address
    expected = {frozenset(group) for size in range(min(k, len(physical_links))+1)
                for group in combinations(sorted(physical_links), size)}
    scenarios = {}
    for path in sorted(directory.glob('*/0_dataplane.txt')):
        failed = set()
        best: dict[str, tuple[int, Route]] = {}
        for line in path.read_text().splitlines():
            if line.startswith('FAILED '):
                endpoints = line.split()[1].split('--')
                if len(endpoints) != 2:
                    raise ValidationError(f'invalid failed link: {line}')
                key = '--'.join(sorted(endpoint.split(':')[0] for endpoint in endpoints))
                if key in failed or key not in physical_links:
                    raise ValidationError(f'unknown or duplicated failed link: {key}')
                failed.add(key)
                continue
            fields = line.split()
            if fields and fields[0] in routers and len(fields) != 10:
                raise ValidationError(f'malformed RIB row: {line}')
            if len(fields) != 10 or fields[0] not in routers or fields[1] != 'default':
                continue
            try:
                prefix = ipaddress.IPv4Network(fields[2])
            except ValueError as exc:
                raise ValidationError(f'malformed RIB prefix: {line}') from exc
            if address not in prefix:
                continue
            peer = None if fields[6] == 'null' else fields[6]
            if peer is not None and peer not in routers:
                raise ValidationError(f'unknown forwarding peer: {peer}')
            interface = 'null_interface' if fields[5].lower() == 'null0' else fields[5]
            route = Route(peer, fields[3], interface, str(prefix))
            if peer is None and fields[3] != 'connected' and interface != 'null_interface':
                raise ValidationError(f'unsupported next-hop representation: {line}')
            previous = best.get(fields[0])
            if previous is not None and previous[0] == prefix.prefixlen:
                raise ValidationError(f'ECMP or duplicate best RIB route at {fields[0]}')
            if previous is None or prefix.prefixlen > previous[0]:
                best[fields[0]] = (prefix.prefixlen, route)
        key = frozenset(failed)
        if key in scenarios:
            raise ValidationError(f'duplicate concrete failure scenario: {sorted(key)}')
        scenarios[key] = ConcreteScenario(key, {node: row[1] for node, row in best.items()}, path)
    if set(scenarios) != expected:
        raise ValidationError(f'incomplete failure universe: expected {len(expected)}, got {len(scenarios)}')
    return scenarios


def delivery(scenario: ConcreteScenario, ingress: str, allowed_finals: set[str]) -> dict:
    """Follow actual next hops; a missing route or a forwarding loop is failure."""
    path = [ingress]
    while True:
        current = path[-1]
        route = scenario.routes.get(current)
        if route is None:
            return dict(path=path, delivered=False, end='no_route')
        if route.interface == 'null_interface':
            return dict(path=path, delivered=False, end='discard')
        if route.peer is None:
            allowed = route.protocol == 'connected' and current in allowed_finals
            return dict(path=path, delivered=allowed, end='allowed_final' if allowed else 'wrong_final')
        if route.peer in path:
            return dict(path=path+[route.peer], delivered=False, end='loop')
        path.append(route.peer)
