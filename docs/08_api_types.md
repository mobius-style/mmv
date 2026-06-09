# 08 API Types

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

Route = Literal["answer", "ask", "verify", "abstain"]
AnswerShape = Literal["low_movement_answer", "admissible_reframing_answer"]

@dataclass
class SessionState:
    session_id: str
    active_language: str = "en"
    facts: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    route_history: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""

@dataclass
class KernelRequest:
    user_input: str
    session_state: SessionState
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AppraisalState:
    completeness: float
    uncertainty: float
    freshness_sensitive: bool
    safety_relevant: bool
    intent_clarity: float
    notes: List[str] = field(default_factory=list)

@dataclass
class RouteDecision:
    route: Route
    reason_codes: List[str]
    confidence_posture: str
    answer_shape: Optional[AnswerShape] = None

@dataclass
class AdapterResponse:
    text: str
    model_used: str
    latency_ms: int
    raw: Dict[str, Any] = field(default_factory=dict)
```
