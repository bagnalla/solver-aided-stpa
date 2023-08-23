# Type and expression language abstract syntax, system data structures.

from __future__ import annotations
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from functools import reduce
from typing import List, Literal, Optional

# # Source metadata. NOT USED YET
# @dataclass
# class Meta:
#     start_line: int
#     end_line: int
#     start_column: int
#     end_column: int

# def metaPretty(m: Meta) -> str:
#     return 'line %s, column %s' % (m.start_line, m.start_column)

@dataclass_json
@dataclass(frozen=True)
class Ident:
    qualifier: Optional[Ident]
    name: str
    
    def __str__(self) -> str:
        if self.qualifier is None:
            return self.name
        else:
            return str(self.qualifier) + '.' + self.name
    
    def toList(self) -> List[str]:
        if self.qualifier:
            return self.qualifier.toList() + [self.name]
        else:
            return [self.name]
    
    @staticmethod
    def ofList(l: List[str]) -> Ident:
        if l:
            if len(l) == 1:
                return Ident(None, l[0])
            else:
                return Ident(Ident.ofList(l[:-1]), l[-1])
        else:
            raise Exception('Ident.ofList: empty list')
    
    @staticmethod
    def ofStr(s: str) -> Ident:
        return Ident.ofList(s.split('.'))

Type = Literal['int', 'bool'] | Ident

@dataclass_json
@dataclass(frozen=True)
class VarDecl:
    name: str
    ty: Type

@dataclass_json
@dataclass(frozen=True)
class FinTypeDecl:
    name: str
    elements: List[str]

@dataclass_json
@dataclass(frozen=True)
class IntLiteral:
    i: int
    
    def __str(self) -> str:
        return str(self.i)

LiteralExpr = IntLiteral | Literal['true', 'false']

@dataclass_json
@dataclass(frozen=True)
class UnaryExpr:
    op: Literal['NOT']
    e: Expr
    
    def __str__(self) -> str:
        return '%s %s' % (self.op, self.e)

@dataclass_json
@dataclass(frozen=True)
class BinaryExpr:
    op: Literal['AND', 'OR', 'LT', 'LE', 'GT', 'GE', 'EQ',
                'PLUS', 'MINUS', 'MULT', 'DIV', 'WHEN']
    e1: Expr
    e2: Expr
    
    def __str__(self) -> str:
        if self.op == 'WHEN':
            return 'WHEN %s, %s' % (self.e1, self.e2)
        else:
            return '%s %s %s' % (self.e1, self.op, self.e2)

Expr = Ident | LiteralExpr | UnaryExpr | BinaryExpr

### Helper constructors for expressions.

# Unary negation.
def neg(e: Expr) -> Expr:
    return UnaryExpr(op = 'NOT', e = e)

# Binary conjunction ('and' is a reserved keyword in Python so we use
# 'land' instead to stand for "logical AND").
def land(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'AND', e1 = e1, e2 = e2)

# Big conjunction of list of expressions.
def conj(es: List[Expr]) -> Expr:
    return reduce(land, es, 'true')

# Binary disjunction ('or' is a reserved keyword in Python so we use
# 'lor' instead to stand for "logical OR").
def lor(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'OR', e1 = e1, e2 = e2)

# Big disjunction of list of expressions.
def disj(es: List[Expr]) -> Expr:
    return reduce(lor, es, 'false')

# Less-than comparison.
def lt(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'LT', e1 = e1, e2 = e2)

# Less-than-or-equal comparison.
def le(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'LE', e1 = e1, e2 = e2)

# Greater-than comparison.
def gt(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'GT', e1 = e1, e2 = e2)

# Greater-than-or-equal comparison.
def ge(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'GE', e1 = e1, e2 = e2)

# Equality comparison.
def eq(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'EQ', e1 = e1, e2 = e2)

# Integer addition.
def plus(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'PLUS', e1 = e1, e2 = e2)

# Integer subtraction.
def minus(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'MINUS', e1 = e1, e2 = e2)

# Integer multiplication.
def mult(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'MULT', e1 = e1, e2 = e2)

# Integer division.
def div(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'DIV', e1 = e1, e2 = e2)

# Logical implication.
def when(e1: Expr, e2: Expr) -> Expr:
    return BinaryExpr(op = 'WHEN', e1 = e1, e2 = e2)

# System data structures.

@dataclass_json
@dataclass(frozen=True)
class Action:
    name:     str        # Name of action (e.g., CA1).
    allowed:  List[Expr] # Constraints on when action is allowed.
    required: List[Expr] # Constraints on when action is required.

@dataclass_json
@dataclass(frozen=True)
class System:
    name:       str               # Name of system.
    types:      List[FinTypeDecl] # Type declarations.
    vars:       List[VarDecl]     # Internal state of system.
    invariants: List[Expr]        # Invariant properties of internal
                                  # state and/or components.
    actions:    List[Action]      # Control actions that can be
                                  # performed by this system/component.
    components: List[System]      # Subsystems / components.

# Just the first two types for now (I believe the other two can be
# simulated via these two anyway).
UCAType = Literal['issued', 'not issued']



@dataclass_json
@dataclass(frozen=True)
class UCA:
    action:  Ident   # Name of action.
    type:    UCAType # Type of UCA.
    context: Expr    # Context in which action is potentially hazardous.
    
    def __str__(self) -> str:
        return 'UCA(action=%s, type=%s, context={%s})' % (self.action, self.type, self.context)

ex_binop: Expr = mult(IntLiteral(10), IntLiteral(1))


# This example came from a typescript representation of the same data and I'm using this as a proof of concept for an api between the two languages
uca_json_ex1 = '{"action":{"qualifier":null,"name":"Action1"},"type":"issued","context":{"op":"MULT","e1":{"i":10},"e2":{"i":1}}}'

## TODO Leaving a print in here just to validate that this works.  This should eventually be removed 
print("Successful parse of json version of UCA data type generated from typescript representation of UCA:" ,UCA.from_json(uca_json_ex1), sep="\n")


# OLD NOTES:
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
