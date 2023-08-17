# Compiling systems to SMT and invoking the solver (currently yices2).

from control import Action, BinaryExpr, conj, disj, eq, Expr, FinTypeDecl, \
    Ident, IntLiteral, neg, System, Type, UCA, UnaryExpr
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple
from yices import Config, Context, Model, Status, Types, Terms
import yices # So we can refer to yices.Type.
Term = int # Make typechecker happy.

def printEnv(env: Mapping[Ident, Term]) -> None:
    for name, tm in env.items():
        print('%s: %s' % (name, tm))

# Compile expressions to yices expressions.
def compileExpr(env: Mapping[Ident, Term], e: Expr) -> Term:
    match e:
        case IntLiteral():
        # case typing.int:
            return Terms.integer(e.i)
        case 'true':
            return Terms.true()
        case 'false':
            return Terms.false()
        case Ident():
            if e in env:
                return env[e]
            else:
                raise Exception('compileExpr: %s not found in environment %s' % (e, env))
        case UnaryExpr():
            return Terms.ynot(compileExpr(env, e.e))
        case BinaryExpr():
            c1, c2 = compileExpr(env, e.e1), compileExpr(env, e.e2)
            if e.op == 'AND':
                return Terms.yand([c1, c2])
            elif e.op == 'OR':
                return Terms.yor([c1, c2])
            else:
                return { 'LT':    Terms.arith_lt_atom,
                         'LE':    Terms.arith_leq_atom,
                         'GT':    Terms.arith_gt_atom,
                         'GE':    Terms.arith_geq_atom,
                         'EQ':    Terms.eq,
                         'PLUS':  Terms.add,
                         'MINUS': Terms.sub,
                         'MULT':  Terms.mul,
                         'DIV':   Terms.idiv,
                         'WHEN':  Terms.implies }[e.op](c1, c2)
        case _:
            raise Exception('compileExpr %s' % e)

# Before asserting any formulas, we first set up the yices context by
# traversing the system and declaring all types and terms. Returns
# dictionaries mapping identifiers to their corresponding yices terms.
def setupYicesContext(sys: System,
                      ) -> Tuple[Context,                   # Yices context.
                                 Dict[Ident, Term],         # Yices term environment.
                                 Dict[Ident, List[Ident]]]: # FinType elements.
    yices_ctx = Context(Config())
    bool_t = Types.bool_type()
    int_t = Types.int_type()
    env: Dict[Ident, Term] = {}
    types: Dict[Ident, yices.Type] = {}
    fintype_els: Dict[Ident, List[Ident]] = {}

    def go(s: System, parent: Optional[Ident]) -> None:
        # Qualifier for current system.
        qualifier: Ident = Ident(parent, s.name)
        
        # Declare enum types.
        for tydecl in s.types:
            name: Ident = Ident(qualifier, tydecl.name)
            elements: List[Ident] = [Ident(qualifier, el) for el in tydecl.elements]
            ty, terms = Types.declare_enum(str(name), [str(el) for el in elements])
            types[name] = ty
            fintype_els[name] = elements
            for el, tm in zip(elements, terms):
                env[el] = tm

        # Declare state variables.
        for vardecl in s.vars:
            name = Ident(qualifier, vardecl.name)
            match vardecl.ty:
                case 'bool':
                    env[name] = Terms.new_uninterpreted_term(bool_t, str(name))
                case 'int':
                    env[name] = Terms.new_uninterpreted_term(int_t, str(name))
                case Ident():
                    env[name] = Terms.new_uninterpreted_term(types[vardecl.ty], str(name))

        # TODO actions.
                
        # Recurse on subsystems.
        for c in s.components:
            go(c, qualifier)

    go(sys, None)
    return yices_ctx, env, fintype_els

# If this ends up being used a lot we can pre-build a dictionary
# (mapping identifiers to actions) to make it more efficient.
def getActionByName(sys: System, name: Ident) -> Action:
    def go(s: System, names: List[str]) -> Action:
        if len(names) > 1:
            if names[0] != s.name:
                raise Exception("getActionByName: expected system '%s', found '%s'" %
                                (names[0], s.name))
            if len(names) == 2:
                # Search in current system.
                for a in s.actions:
                    if a.name == names[1]:
                        return a
                raise Exception("getActionByName: system '%s' has no action named '%s'" %
                                (s.name, names[1]))
            else:
                # Recursively search subsystems.
                for c in s.components:
                    if c.name == names[1]:
                        return go(c, names[1:])
                raise Exception("getActionByName: system '%s' no component named '%s'" %
                                (s.name, names[1]))
        else:
            raise Exception("getActionByName: impossible. name: '%s'" % name)
    return go(sys, name.toList())

# Assert conjunction of all invariants:
# conj_inv(sys) ≜ ⋀sys.invariants ∧ ⋀{conj_inv(c) | c ∈ sys.components}.
def assertInvariants(yices_ctx: Context, env: Dict[Ident, Term], sys: System) -> None:
    yices_ctx.assert_formulas([compileExpr(env, e) for e in sys.invariants])
    for c in sys.components:
        assertInvariants(yices_ctx, env, c)
    if yices_ctx.check_context() == Status.UNSAT:
        raise Exception('System assumptions are impossible.')

# A scenario is a mapping from identifiers to values. A value is (for
# now) either a bool, int, or string denoting a fintype element.
@dataclass
class Scenario:
    dict: Dict[Ident, bool | int | Ident]
    def __getitem__(self, key: Ident) -> bool | int | Ident:
        return self.dict[key]
    def __setitem__(self, key: Ident, value: bool | int | Ident) -> None:
        self.dict[key] = value
    def __str__(self) -> str:
        return '{%s}' % ', '.join('%s: %s' % (key, value) for key, value in self.dict.items())
    def items(self) -> List[Tuple[Ident, bool | int | Ident]]:
        return list(self.dict.items())

# Convert a yices model to a Scenario.
def scenarioFromModel(yices_ctx: Context,                       # Yices context.
                      ctx: Mapping[Ident, Type],                # Typing context.
                      env: Mapping[Ident, Term],                # Map variables to yices terms.
                      fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                      model: Model                              # Model produced by yices.
                      ) -> Scenario:                            # Scenario derived from model.
    defined_terms = model.collect_defined_terms()
    scenario: Scenario = Scenario({})
    for name, term in env.items():
        if name not in fintype_els and term in defined_terms:
            ty: Type = ctx[name]
            match ty:
                case 'bool':
                    scenario[name] = model.get_bool_value(term)
                case 'int':
                    scenario[name] = model.get_integer_value(term)
                case Ident():
                    scenario[name] = fintype_els[ty][model.get_scalar_value(term)]
    return scenario

# Verify UCAs against action constraints (check that the UCAs are
# ruled out by the constraints). For each UCA u and corresponding
# action a, need to verify:

# For 'when issued' UCA:
# ∀ system states, ⋀a.constraints ⇒ ¬u.context
# ⇔ ~ (∃ system state, ~(⋀a.constraints ⇒ ¬u.context))
# ⇔ ~ (∃ system state, ~(~⋀a.constraints ∨ ¬u.context))
# ⇔ ~ (∃ system state, ⋀a.constraints ∧ u.context).

# I.e., check unsatisfiability of the conjunction of all the
# constraints with the UCA context.

# For 'when not issued' UCA:
# ∀ system states, u.context ⇒ ⋀a.constraints
# ⇔ ~ (∃ system state, ¬(u.context ⇒ ⋀a.constraints))
# ⇔ ~ (∃ system state, ¬(¬u.context ∨ ⋀a.constraints))
# ⇔ ~ (∃ system state, u.context ∧ ¬⋀a.constraints)
# ⇔ ~ (∃ system state, u.context ∧ ⋁{¬P | P ∈ a.constraints}).

# I.e., check unsatisfiability of conjunction of UCA context with
# disjunction of negated constraints.

def checkConstraints(yices_ctx: Context,                       # Yices context.
                     ctx: Mapping[Ident, Type],                # Typing context.
                     env: Mapping[Ident, Term],                # Map variables to yices terms.
                     fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                     sys: System,                              # System to check.
                     ucas: Sequence[UCA]                       # UCAs to check.
                     ) -> Optional[Scenario]:                  # Return counterexample if found.
    for u in ucas:
        print('Checking %s' % u)
        yices_ctx.push()
        
        a = getActionByName(sys, u.action)

        if u.type == 'issued':
            yices_ctx.assert_formula(compileExpr(env, conj(a.constraints + [u.context])))
        else: # u.type == 'not_issued'
            yices_ctx.assert_formula(
                compileExpr(env, conj([u.context, disj([neg(e) for e in a.constraints])])))
        
        if yices_ctx.check_context() == Status.SAT:
            model = Model.from_context(yices_ctx, 1)
            yices_ctx.pop()
            return scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
        else:
            print('UCA verified!')
        
        yices_ctx.pop()

    return None

# Generate scenarios compatible with action constraints.
def genScenarios(yices_ctx: Context,                       # Yices context.
                 ctx: Mapping[Ident, Type],                # Typing context.
                 env: Mapping[Ident, Term],                # Map variables to yices terms.
                 fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                 sys: System                               # System to generate scenarios for.
                 ) -> Dict[str, List[Scenario]]:           # Map action names to lists of scenarios.
    
    # For each action, assert conjunction of its constraints and
    # enumerate models (assignments of variables that satisfy all the
    # constraints while being consistent with all the component
    # invariants which are assumed to have already been asserted in
    # the given yices context).
    
    scenarios: Dict[str, List[Scenario]] = {}
    for c in sys.components:
        for a in c.actions:
            scenarios[a.name] = []
            yices_ctx.push()
            yices_ctx.assert_formulas([compileExpr(env, e) for e in a.constraints])
            while yices_ctx.check_context() == Status.SAT:
                model = Model.from_context(yices_ctx, 1)
                scenario = scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
                scenarios[a.name].append(scenario)
                es: List[Expr] = []
                for name, val in scenario.items():
                    if isinstance(val, bool):
                        es.append(eq(name, 'true' if val else 'false'))
                    elif isinstance(val, int):
                        es.append(eq(name, IntLiteral(int(val))))
                    else:
                        es.append(eq(name, val))
                yices_ctx.assert_formula(compileExpr(env, neg(conj(es))))
            yices_ctx.pop()
    return scenarios
