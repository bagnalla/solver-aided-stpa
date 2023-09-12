from enum import IntEnum
from typing import List, Optional, Tuple

# These types are not perfect (more restrictive than the actual API in
# some places) but should be good enough for our purposes.

Term = int

class Type: ...

class Config: ...

class Status(IntEnum):
    IDLE        = 0
    SEARCHING   = 1
    UNKNOWN     = 2
    SAT         = 3
    UNSAT       = 4
    INTERRUPTED = 5
    ERROR       = 6

class Context():
    def __init__(self, config: Optional[Config] = None): ...
    def assert_formula(self, term: Term) -> bool: ...
    def assert_formulas(self, terms: List[Term]) -> bool: ...
    def push(self) -> bool: ...
    def pop(self) -> bool: ...
    def check_context(self, timeout: Optional[float] = None) -> Status: ...
    def dispose(self) -> None: ...

class Model:
    def collect_defined_terms(self) -> List[Term]: ...
    def get_bool_value(self, term: Term) -> bool: ...
    def get_integer_value(self, term: Term) -> int: ...
    def get_scalar_value(self, term: Term) -> int: ...
    @staticmethod
    def from_context(context: Context, keep_subst: int) -> Model: ...

class Types:
    @staticmethod
    def bool_type(name: Optional[str] = None) -> Type: ...
    @staticmethod
    def int_type(name: Optional[str] = None) -> Type: ...
    @staticmethod
    def declare_enum(name: str, element_names: List[str]) -> Tuple[Type, List[Term]]: ...

class Terms:
    @staticmethod
    def integer(value: int) -> Term: ...
    @staticmethod
    def true() -> Term: ...
    @staticmethod
    def false() -> Term: ...
    @staticmethod
    def ynot(t: Term) -> Term: ...
    @staticmethod
    def yand(ts: List[Term]) -> Term: ...
    @staticmethod
    def yor(ts: List[Term]) -> Term: ...
    @staticmethod
    def arith_lt_atom(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def arith_leq_atom(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def arith_gt_atom(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def arith_geq_atom(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def eq(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def add(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def sub(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def mul(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def idiv(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def implies(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def iff(lhs: Term, rhs: Term) -> Term: ...
    @staticmethod
    def new_uninterpreted_term(tau: Type, name: Optional[str] = None) -> Term: ...
