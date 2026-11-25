"""Scoped SMT queries on a reusable process; standalone evidence remains replayable."""
import os
import selectors
import subprocess
import time


class SolverSession:
    def __init__(self):
        self.process = None
        self.sorts = {}
        self.starts = 0
        self.exchanges = 0
        self.executable = None

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        self.sorts = {}

    def execute(self, executable, document, commands, timeout):
        if self.process is not None and self.executable != str(executable):
            self.close()
        if self.process is not None and any(
                name in self.sorts and self.sorts[name] != sort
                for name, sort in document.declarations.items()):
            self.close()
        if self.process is None:
            self.process = subprocess.Popen([str(executable), '-in', '-smt2'],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT)
            self.starts += 1
            self.executable = str(executable)
        process = self.process
        declarations = [form for (name, _), form in zip(
            document.declarations.items(), document.declaration_forms) if name not in self.sorts]
        self.sorts.update(document.declarations)
        self.exchanges += 1
        marker = f'plus_query_end_{self.exchanges}'
        # Assertions and tactic applications are scoped; timeout/error destroys
        # the process, so no partially consumed response can contaminate a query.
        payload = '\n'.join(['(set-option :print-success false)', *declarations,
                              '(push 1)', *commands, '(pop 1)', f'(echo "{marker}")', ''])
        started = time.monotonic()
        chunks = bytearray()
        try:
            pending = memoryview(payload.encode())
            os.set_blocking(process.stdin.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                selector.register(process.stdin, selectors.EVENT_WRITE)
                while True:
                    remaining = timeout - (time.monotonic() - started)
                    ready = selector.select(max(0, remaining))
                    if remaining <= 0 or not ready:
                        raise subprocess.TimeoutExpired(str(executable), timeout)
                    for key, _ in ready:
                        if key.fileobj is process.stdin:
                            written = os.write(process.stdin.fileno(), pending[:65536])
                            pending = pending[written:]
                            if not pending:
                                selector.unregister(process.stdin)
                        else:
                            chunk = os.read(process.stdout.fileno(), 65536)
                            if not chunk:
                                raise OSError('incremental solver exited before query completion')
                            chunks.extend(chunk)
                            if chunks.endswith((marker + '\n').encode()):
                                result = bytes(chunks[:-len(marker)-1]).decode()
                                if '(error' in result:
                                    self.close()
                                return result
        except BaseException:
            self.close()
            raise
