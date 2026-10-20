from dataclasses import asdict, dataclass, field


@dataclass
class Finding:
    path: str
    line: int
    code: str
    message: str
    level: str = "error"
    # Automatic repair `udb verify --fix` may apply: replace `old` with `new` on `line`.
    fix: dict | None = field(default=None, compare=False)

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.level}  {self.code}\n    {self.message}"

    def as_dict(self) -> dict:
        return asdict(self)


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]


def as_text(findings: list[Finding]) -> str:
    return "\n".join(str(f) for f in findings) if findings else "OK. No problems found."
