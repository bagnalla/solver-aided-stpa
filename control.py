from __future__ import annotations
from dataclasses import dataclass
from functools import reduce
from typing import assert_never, cast, Dict, List, Literal, Optional, Tuple

# Type and expression language abstract syntax.

@dataclass(frozen=True)
class NamedType:
    name: str

Type = Literal['int', 'bool'] | NamedType

@dataclass(frozen=True)
class TypeDecl:
    name: str
    elements: List[str]

@dataclass(frozen=True)
class VarDecl:
    name: str
    ty: Type

@dataclass(frozen=True)
class IntLiteral:
    i: int

LiteralExpr = IntLiteral | Literal['true', 'false']

@dataclass(frozen=True)
class NameExpr:
    qualifier: Optional[str]
    name: str
    def __str__(self) -> str:
        if self.qualifier is None:
            return self.name
        else:
            return self.qualifier + '_' + self.name

@dataclass(frozen=True)
class UnaryExpr:
    op: Literal['NOT']
    e: Expr

@dataclass(frozen=True)
class BinaryExpr:
    op: Literal['AND', 'OR', 'LT', 'LE', 'GT', 'GE', 'EQ',
                'PLUS', 'MINUS', 'MULT', 'DIV', 'WHEN']
    e1: Expr
    e2: Expr

Expr = NameExpr | LiteralExpr | UnaryExpr | BinaryExpr

# Helper constructors for expressions.

# Unary negation.
def neg(e: Expr) -> Expr:
    return UnaryExpr(op = 'NOT', e = e)

# Big conjunction of list of expressions.
def conj(es: List[Expr]) -> Expr:
    return reduce(lambda a, b: BinaryExpr(op = 'AND', e1 = a, e2 = b), es, 'true')

# Big disjunction of list of expressions.
def disj(es: List[Expr]) -> Expr:
    return reduce(lambda a, b: BinaryExpr(op = 'OR', e1 = a, e2 = b), es, 'false')

# Equality comparison.
def eq(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'EQ', e1 = e1, e2 = e2)

# Implication.
def when(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'WHEN', e1 = e1, e2 = e2)

# System data structures.

@dataclass(frozen=True)
class Action:
    name:        str        # Name of action (e.g., CA1).
    constraints: List[Expr] # Safety constraints on action.

@dataclass(frozen=True)
class Component:
    name:      str           # Name of component.
    state:     List[VarDecl] # Internal state of component.
    invariant: Expr          # Invariant property of internal state.
    actions:   List[Action]  # Control actions that can be performed
                             # by this component.

@dataclass(frozen=True)
class System:
    name:         str             # Name of system.
    types:        List[TypeDecl]  # Type declarations.
    components:   List[Component] # A collection of components.
    assumptions:  List[Expr]      # Global system assumptions.

# Just the first two types for now (I believe the other two can be
# simulated via these two anyway).
UCAType = Literal['issued', 'not issued']

@dataclass(frozen=True)
class UCA:
    action:  str     # Name of action.
    type:    UCAType # Type of UCA.
    context: Expr    # Context in which action is potentially hazardous.

# Safety constraints on Actions are Boolean-valued expressions that
# can refer to fields of Components, (e.g., 'World.runway_status ==
# DRY' if there is a Component named 'World' with field
# 'runway_status' whose possible values include 'DRY').

# After the System and a collection of UCAs are defined by the user
# (UCAs defined separately via a context table or something
# equivalent), the tool can:

# 1) Look for system states that are simultaneously consistent with
# all action constraints and one of the UCAs (thus being potentially
# hazardous and indicating that additional action constraints are
# needed).

# 2) Recommend additional action constraints?

# 3) When 1) is unsat (action constraints are sufficient to rule out
# UCAs), explore system states that are consistent with all the action
# constraints to look for other potential hazards the analyst may not
# have considered. E.g., for a UCA that says something like "issuing
# 'activate_brakes' action when 'Aircraft.flight_status == TAKEOFF'
# causes hazard", a corresponding constraint on the 'activate_brakes
# action might be 'Aircraft.flight_status != TAKEOFF', and the tool
# can generate system states (configurations of state variables for
# all components) where 'Aircraft.flight_status != TAKEOFF' is true
# and all invariants are respected (e.g., there may be an invariant
# that relates Aircraft.flight_status to some other variables, so that
# the constraint 'Aircraft.flight_status != TAKEOFF' implies
# constraints on those other variables as well).

# Typechecking systems (a well-typed system can be checked by the
# solver without the solver throwing an error).

@dataclass(frozen=True)
class TypeError(Exception):
    msg: str

def buildTypingCtx(s: System) -> Dict[str, Type]:
    ctx: Dict[str, Type] = {}
    for decl in s.types:
        for el in decl.elements:
            if el in ctx:
                raise TypeError("Duplicate FinType element: '%s'" % el)
            else:
                ctx[el] = NamedType(decl.name)
    for c in s.components:
        for var in c.state:
            ctx[c.name + '_' + var.name] = var.ty
    return ctx

def tycheckExpr(e: Expr, ctx: Dict[str, Type]) -> Type:
    match e:
        case IntLiteral():
            return 'int'
        case 'true' | 'false':
            return 'bool'
        case NameExpr():
            if str(e) in ctx:
                return ctx[str(e)]
            else:
                raise TypeError("Unknown name '%s'" % e)
        case UnaryExpr():
            if e.op == 'NOT':
                if tycheckExpr(e.e, ctx) == 'bool':
                    return 'bool'
                else:
                    raise TypeError(msg = 'Expected type bool')
        case BinaryExpr():
            ty1, ty2 = tycheckExpr(e.e1, ctx), tycheckExpr(e.e2, ctx)
            if type(ty1) != type(ty2):
                raise TypeError('Arguments to binary expression should have the same type')
            if e.op == 'EQ':
                return 'bool'
            elif e.op in ['LT', 'LE', 'GT', 'GE']:
                if ty1 == 'int':
                    return 'bool'
                else:
                    raise TypeError('Expected type int')
            elif e.op in ['PLUS', 'MINUS', 'MULT', 'DIV']:
                if ty1 == 'int':
                    return 'int'
                else:
                    raise TypeError('Expected type int')
            else: # e.op in ['AND', 'OR', 'WHEN']:
                if ty1 == 'bool':
                    return 'bool'
                else:
                    raise TypeError('Expected type bool')
        case _:
            assert_never(e)

def tycheckAction(a: Action, ctx: Dict[str, Type]):
    for c in a.constraints:
        if tycheckExpr(c, ctx) != 'bool':
            raise TypeError('constraint must have type bool')

def tycheckComponent(c: Component, ctx: Dict[str, Type]):
    if tycheckExpr(c.invariant, ctx) != 'bool':
        raise TypeError('invariant must have type bool')
    for a in c.actions:
        tycheckAction(a, ctx)

def tycheckSystem(s: System, ctx: Dict[str, Type]):
    for c in s.components:
        tycheckComponent(c, ctx)
    for e in s.assumptions:
        if tycheckExpr(e, ctx) != 'bool':
            raise TypeError('system assumption must have type bool')

def tycheckUCA(u: UCA, ctx: Dict[str, Type]):
    # Ensuring that the action named in the UCA is a known control
    # action can happen later when doing SMT stuff, but it could be
    # good to check for it here as well.
    if tycheckExpr(u.context, ctx) != 'bool':
        raise TypeError('context expression of UCA must have type bool')    
