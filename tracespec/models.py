from dataclasses import dataclass, field
from enum import Enum


class SpanType(str, Enum):
    LLM = "LLM"
    TOOL = "TOOL"
    AGENT = "AGENT"
    CHAIN = "CHAIN"
    RETRIEVER = "RETRIEVER"
    UNKNOWN = "UNKNOWN"


@dataclass
class Span:
    id: str
    trace_id: str
    parent_id: str | None
    type: SpanType
    name: str
    attrs: dict
    start_ms: int
    end_ms: int
    error: str | None = None
    children: list["Span"] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.children = []

    def add_child(self, span: "Span") -> None:
        self.children.append(span)

    def depth(self) -> int:
        if not self.children:
            return 0
        return 1 + max(child.depth() for child in self.children)


@dataclass
class Session:
    trace_id: str
    agent_name: str
    provider: str | None
    started_at: str
    spans: list[Span]
    verdict: str = "ok"

    def root(self) -> Span:
        by_id = {span.id: span for span in self.spans}
        for span in self.spans:
            span.children = []
        roots = [span for span in self.spans if span.parent_id not in by_id]
        if not roots:
            raise ValueError("session has no root span")
        for span in self.spans:
            if span.parent_id in by_id:
                by_id[span.parent_id].add_child(span)
        return roots[0]

    def all_spans(self) -> list[Span]:
        return self.spans


@dataclass
class Assertion:
    type: str
    tool: str | None = None
    params: dict | None = None
    schema: dict | None = None
    max_cost: float | None = None
    max_latency_ms: int | None = None
    rubric: str | None = None
    min_score: int = 3


@dataclass
class Case:
    id: str
    suite: str
    name: str
    tier: str
    input: dict
    assertions: list[Assertion]
    source_trace_id: str


@dataclass
class Suite:
    name: str
    version: int
    tier: str
    case_ids: list[str]
    baseline: dict[str, float] = field(default_factory=dict)


@dataclass
class RunResult:
    case_id: str
    passed: bool
    pass_rate: float
    trials_passed: int
    trials: int
    cost_usd: float
    latency_ms: int
    error: str | None


@dataclass
class Run:
    id: str
    suite: str
    tier: str
    status: str
    results: list[RunResult]


@dataclass
class Cluster:
    id: str
    agent_name: str
    signature: str
    label: str
    count: int
    trace_ids: list[str]


@dataclass
class Proposal:
    id: str
    patch: dict
    status: str
    verdict: dict
