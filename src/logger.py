from dataclasses import dataclass, field


@dataclass
class LogNode:
    message: str
    children: list["LogNode"] = field(default_factory=list)


class Logger:
    def __init__(self):
        self.root = []
        self.stack = []

    def __call__(self, message: str):
        node = LogNode(message=message)

        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.root.append(node)

        return _Scope(self, node)


class _Scope:
    def __init__(self, logger, node):
        self.logger = logger
        self.node = node

    def __enter__(self):
        self.logger.stack.append(self.node)
        return self.node

    def __exit__(self, exc_type, exc, tb):
        self.logger.stack.pop()


def _get_logs_in(nodes, indent=0):
    logs = []
    for node in nodes:
        logs.append("-" * indent + node.message)
        _get_logs_in(node.children, indent + 1)
    return logs


log = Logger()


def get_logs():
    return _get_logs_in(log.root)


def reset_logs():
    log.root = []
    log.stack = []
