# Typechecking systems (a well-typed system can be checked by the
# solver without the solver throwing an error).

from control import Action, BinaryExpr, Expr, FloatLiteral, \
    Ident, IntLiteral, System, Type, UCA, UnaryExpr
from dataclasses import dataclass
from typing import Dict, Generic, List, Mapping, Optional, Set, TypeVar

@dataclass(frozen=True)
class TypeError(Exception):
    msg: str

# QUESTION: Do we want to enforce lexical scoping rules? The current
# setup (using a flat dictionary) allows expressions to refer to
# variables/actions of any component in the system regardless of their
# relative positions in the system hierarchy. We might want them to
# only be able to reference direct parents/children? I suppose we
# could enforce any rules like that even with the flat dictionary --
# and we have flexibility to enforce whatever rules we want that way
# -- but I was thinking that it might be easier with a nested symbol
# table representation for contexts/environments.

def buildTypingCtx(sys: System) -> Dict[Ident, Type]:
    ctx: Dict[Ident, Type] = {} # Typing context.
    types: List[Type] = []      # Declared types.
    
    def go(s: System, parent: Optional[Ident]) -> None:
        # Qualifier for current system.
        qualifier: Ident = Ident(parent, s.name)
    
        # Type declarations.
        seen: List[str] = []
        for tydecl in s.types:
            types.append(Ident(qualifier, tydecl.name))
            for el in tydecl.elements:
                if Ident(qualifier, el) in ctx:
                    raise TypeError("Duplicate FinType element: '%s'" % el)
                else:
                    ctx[Ident(qualifier, el)] = Ident(qualifier, tydecl.name)

        # State variables. Keep using the same 'seen' list to prevent
        # reusing fintype element names as variables.
        for vardecl in s.vars:
            if vardecl.name in seen:
                raise TypeError("Duplicate variable: '%s'" % vardecl.name)
            elif isinstance(vardecl.ty, Ident) and vardecl.ty not in types:
                raise TypeError("Unknown type: '%s'" % vardecl.ty)
            else:
                seen.append(vardecl.name)
            ctx[Ident(qualifier, vardecl.name)] = vardecl.ty

        # Actions. Disallow the current action from appearing in its
        # own constraints to avoid paradoxical assertions like "an
        # action is allowed iff it's not allowed".
        
        # TODO: should it be possible for an action's 'allowed'
        # variable to appear in its 'required' constraints, or vice
        # versa? E.g., could there be a constraint like "this action
        # is required when it's allowed and ..." or "this action is
        # allowed when it's required or ...".
        for a in s.actions:
            seen.append(a.name)
            action_name = Ident(qualifier, a.name)
            allowed_name = Ident(action_name, 'allowed')
            required_name = Ident(action_name, 'required')
            vars: Set[Ident] = set().union(*([fvs(e) for e in a.allowed] +
                                             [fvs(e) for e in a.required]))
            if allowed_name in vars:
                raise TypeError("'%s' appears in constraint for action '%s'" %
                                (allowed_name, a.name))
            if required_name in vars:
                raise TypeError("'%s' appears in constraint for action '%s'" %
                                (required_name, a.name))
            ctx[allowed_name] = 'bool'
            ctx[required_name] = 'bool'

        # Recurse on subsystems.
        for c in s.components:
            if c.name in seen:
                raise TypeError("Component name '%s' already used" % c.name)
            go(c, qualifier)

    go(sys, None)
    return ctx

# Free variables of an expression (i.e., the set of variables that
# appear in the expression).
def fvs(e: Expr) -> Set[Ident]:
    match e:
        case Ident():
            return { e }
        case IntLiteral() | FloatLiteral() | 'true' | 'false':
            return set()
        case UnaryExpr():
            return fvs(e.e)
        case BinaryExpr():
            return fvs(e.e1).union(fvs(e.e2))

def printCtx(ctx: Mapping[Ident, Type]) -> None:
    for name, ty in ctx.items():
        print('%s: %s' % (name, ty))

def tycheckExpr(e: Expr, ctx: Mapping[Ident, Type]) -> Type:
    match e:
        case IntLiteral():
            return 'int'
        case FloatLiteral():
            return 'real'
        case 'true' | 'false':
            return 'bool'
        case Ident():
            if e in ctx:
                return ctx[e]
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
                if ty1 in ['int', 'real']:
                    return 'bool'
                else:
                    raise TypeError('Expected type int')
            elif e.op in ['PLUS', 'MINUS', 'MULT', 'DIV']:
                if ty1 in['int', 'real']:
                    return 'int'
                else:
                    raise TypeError('Expected type int')
            else: # e.op in ['AND', 'OR', 'WHEN']:
                if ty1 == 'bool':
                    return 'bool'
                else:
                    raise TypeError('Expected type bool')

def tycheckAction(a: Action, ctx: Mapping[Ident, Type]) -> None:
    for e in a.allowed:
        if tycheckExpr(e, ctx) != 'bool':
            raise TypeError('constraint must have type bool')
    for e in a.required:
        if tycheckExpr(e, ctx) != 'bool':
            raise TypeError('constraint must have type bool')

def tycheckSystem(s: System, ctx: Mapping[Ident, Type]) -> None:
    for e in s.invariants:
        if tycheckExpr(e, ctx) != 'bool':
            raise TypeError('system invariant must have type bool')
    for a in s.actions:
        tycheckAction(a, ctx)
    for c in s.components:
        tycheckSystem(c, ctx)

def tycheckUCA(u: UCA, ctx: Mapping[Ident, Type]) -> None:
    # Ensuring that the action named in the UCA is a known control
    # action can happen later when doing SMT stuff, but it could be
    # good to check for it here as well.
    if tycheckExpr(u.context, ctx) != 'bool':
        raise TypeError('context expression of UCA must have type bool')
