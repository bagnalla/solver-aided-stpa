# Compiling systems to SMT and invoking the solver (currently yices2).

from control import Action, BinaryExpr, conj, disj, eq, Expr, FloatLiteral, \
    FinTypeDecl, Ident, IntLiteral, land, lor, neg, System, Type, UCA, UnaryExpr
from dataclasses import dataclass
from typing import Dict, List, Mapping, Iterator, Optional, Sequence, Tuple
from yices import Config, Context, Model, Status, Types, Terms
import yices # So we can refer to yices.Type.
Term = int # Make typechecker happy.

# TODO: It might be nice to (somewhere, perhaps not in this tool but
# in the plugin that invokes it, with whatever necessary support from
# this tool) report to the user which losses are still possible given
# the current specification. I.e., gather all unverified UCAs and
# their associated losses, and let the user decide if/when to see a
# counterexample that leads to each one.

@dataclass(frozen=True)
class SolverError(Exception):
    msg: str

def printEnv(env: Mapping[Ident, Term]) -> None:
    for name, tm in env.items():
        print('%s: %s' % (name, tm))

# Compile expressions to yices expressions.
def compileExpr(env: Mapping[Ident, Term], e: Expr) -> Term:
    match e:
        case IntLiteral():
            return Terms.integer(e.i)
        case FloatLiteral():
            return Terms.parse_float(e.f)
        case 'true':
            return Terms.true()
        case 'false':
            return Terms.false()
        case Ident():
            if e in env:
                return env[e]
            else:
                raise SolverError('compileExpr: %s not found in environment %s' % (e, env))
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

# Set up the yices context by traversing the system and declaring all
# types and terms. Returns dictionaries mapping identifiers to their
# corresponding yices terms.
def setupYicesContext(ctx: Mapping[Ident, Type], # Typing context.
                      sys: System,               # System.
                      ) -> Tuple[Context,                   # Yices context.
                                 Dict[Ident, Term],         # Yices term environment.
                                 Dict[Ident, List[Ident]]]: # FinType elements.
    bool_t: yices.Type = Types.bool_type()     # Shorthand for yices bool type.
    int_t: yices.Type = Types.int_type()       # Shorthand for yices int type.
    
    yices_ctx: Context = Context(Config())     # Yices context.
    env: Dict[Ident, Term] = {}                # Yices term environment.
    types: Dict[Ident, yices.Type] = {}        # Yices type environment.
    fintype_els: Dict[Ident, List[Ident]] = {} # FinType elements.

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

        # Actions.
        for a in s.actions:
            action_name = Ident(qualifier, a.name)
            allowed_name = Ident(action_name, 'allowed')
            required_name = Ident(action_name, 'required')
            env[allowed_name] = Terms.new_uninterpreted_term(bool_t, str(allowed_name))
            env[required_name] = Terms.new_uninterpreted_term(bool_t, str(required_name))

            # a.allowed ⇔ ⋀a.allowed.
            yices_ctx.assert_formula(Terms.iff(env[allowed_name],
                                               compileExpr(env, conj(a.allowed))))
            if yices_ctx.check_context() == Status.UNSAT:
                raise SolverError("Action '%s' 'allowed' assumptions are ill-formed" %
                                  action_name)
            
            # a.required ⇔ ⋁a.required.
            yices_ctx.assert_formula(Terms.iff(env[required_name],
                                               compileExpr(env, disj(a.required))))
            if yices_ctx.check_context() == Status.UNSAT:
                raise SolverError("Action '%s' 'required' assumptions are ill-formed" %
                                  action_name)
            
            # Check that allowed and required constraints are
            # consistent. I.e., that required implies allowed, or
            # equivalently, that not allowed implies not required.
            # TODO: this should probably be done later, after
            # asserting system invariants.
            yices_ctx.push()
            yices_ctx.assert_formula(Terms.yand([env[required_name],
                                                 Terms.ynot(env[allowed_name])]))
            if yices_ctx.check_context() == Status.SAT:
                model = Model.from_context(yices_ctx, 1)
                yices_ctx.pop()
                raise SolverError("Action '%s' required but not allowed in scenario %s" %
                                  (action_name,
                                   scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)))
            yices_ctx.pop()
            
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
                raise SolverError("getActionByName: expected system '%s', found '%s'" %
                                  (names[0], s.name))
            if len(names) == 2:
                # Search in current system.
                for a in s.actions:
                    if a.name == names[1]:
                        return a
                raise SolverError("getActionByName: system '%s' has no action named '%s'" %
                                  (s.name, names[1]))
            else:
                # Recursively search subsystems.
                for c in s.components:
                    if c.name == names[1]:
                        return go(c, names[1:])
                raise SolverError("getActionByName: system '%s' no component named '%s'" %
                                  (s.name, names[1]))
        else:
            raise SolverError("getActionByName: impossible. name: '%s'" % name)
    return go(sys, name.toList())

# Assert conjunction of all invariants:
# conj_inv(sys) ≜ ⋀sys.invariants ∧ ⋀{conj_inv(c) | c ∈ sys.components}.
def assertInvariants(yices_ctx: Context,
                     env: Dict[Ident, Term],
                     sys: System) -> None:
    yices_ctx.assert_formulas([compileExpr(env, e) for e in sys.invariants])
    if yices_ctx.check_context() == Status.UNSAT:
        raise SolverError("System '%s' invariants are unsatisfiable." % sys.name)
    for c in sys.components:
        assertInvariants(yices_ctx, env, c)

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
# TODO: provide option to print generated variables (e.g., action variables)?
def scenarioFromModel(yices_ctx: Context,                       # Yices context.
                      ctx: Mapping[Ident, Type],                # Typing context.
                      env: Mapping[Ident, Term],                # Map variables to yices terms.
                      fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                      model: Model                              # Model produced by yices.
                      ) -> Scenario: # Scenario derived from model.
    defined_terms = model.collect_defined_terms()
    scenario: Scenario = Scenario({})
    for name, term in env.items():
        if name not in fintype_els and term in defined_terms \
           and ctx[name] != Ident(None, 'action'):
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
# ∀ system states, u.context ⇒ ¬⋀a.allowed.
# Or, equivalently:
# ∀ system states, ⋀a.allowed ⇒ ¬u.context
# ⇔ ¬(∃ system state, ¬(⋀a.allowed ⇒ ¬u.context))
# ⇔ ¬(∃ system state, ¬(¬⋀a.allowed ∨ ¬u.context))
# ⇔ ¬(∃ system state, ⋀a.allowed ∧ u.context).

# I.e., check unsatisfiability of the conjunction of all the 'allowed'
# constraints with the UCA context. Or:

# ∀ system states, u.context ⇒ ¬⋁a.required.
# Or, equivalently:
# ∀ system states, ⋁a.required ⇒ ¬u.context
# ⇔ ¬(∃ system state, ¬(⋁a.required ⇒ ¬u.context))
# ⇔ ¬(∃ system state, ¬(¬⋁a.required ∨ ¬u.context))
# ⇔ ¬(∃ system state, ⋁a.required ∧ u.context).

# Combining the above into a single assertion:
# ¬(∃ system state, u.context ∧ (⋀a.allowed ∨ ⋁a.required)).

# I.e., there should not exist a system state in which the UCA context
# is true and the action is allowed or required.

# For 'when not issued' UCA:
# ∀ system states, u.context ⇒ ⋀a.allowed
# ⇔ ¬(∃ system state, ¬(u.context ⇒ ⋀a.allowed))
# ⇔ ¬(∃ system state, ¬(¬u.context ∨ ⋀a.allowed))
# ⇔ ¬(∃ system state, u.context ∧ ¬⋀a.allowed)

# I.e., check unsatisfiability of conjunction of UCA context with
# disjunction of negated constraints. And:

# ∀ system states, u.context ⇒ ⋁a.required
# ⇔ ¬(∃ system state, ¬(u.context ⇒ ⋁a.required))
# ⇔ ¬(∃ system state, ¬(¬u.context ∨ ⋁a.required))
# ⇔ ¬(∃ system state, u.context ∧ ¬⋁a.required)

# Combining the above into a single assertion:
# ¬(∃ system state, u.context ∧ ¬⋀a.allowed ∧ ¬⋁a.required)

# I.e., there should not exist a system state in which the UCA context
# is true and the action is not allowed and not required.

def checkConstraints(yices_ctx: Context,                       # Yices context.
                     ctx: Mapping[Ident, Type],                # Typing context.
                     env: Mapping[Ident, Term],                # Map variables to yices terms.
                     fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                     sys: System,                              # System to check.
                     ucas: Sequence[UCA]                       # UCAs to check.
                     ) -> Optional[Scenario]: # Return counterexample if found.
    for u in ucas:
        print('Checking %s' % u)
        yices_ctx.push()
        
        a = getActionByName(sys, u.action)
        allowed = Ident(u.action, 'allowed')
        required = Ident(u.action, 'required')

        # Assert formulas described by above comments.
        if u.type == 'issued':
            yices_ctx.assert_formula(compileExpr(env, land(u.context, lor(allowed, required))))
        else: # u.type == 'not_issued'
            yices_ctx.assert_formula(compileExpr(env, conj([u.context,
                                                            neg(allowed), neg(required)])))
        
        if yices_ctx.check_context() == Status.SAT:
            model = Model.from_context(yices_ctx, 1)
            yices_ctx.pop()
            return scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
        else:
            print('UCA verified!')
        
        yices_ctx.pop()

    return None

# TODO: Add a way to filter out action variables. There should
# probably be a configuration parameter(s) for the caller to choose
# which kinds of variables are included in the generated scenarios.

# Generate scenarios compatible with action 'allowed'
# constraints. WARNING: this generator temporarily modifies the yices
# context. The context is restored to its initial state once the
# generator is finished. If you want to stop using the generator early
# (perhaps it never terminates) you can call .pop() on the context to
# restore it yourself (but you will have to stop using the generator
# after that point or else it might erroneously pop the context again).
def genAllowedScenarios(yices_ctx: Context,                       # Yices context.
                        ctx: Mapping[Ident, Type],                # Typing context.
                        env: Mapping[Ident, Term],                # Map variables to yices terms.
                        fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                        action: Action
                        ) -> Iterator[Scenario]:
    yices_ctx.push()
    yices_ctx.assert_formula(compileExpr(env, conj(action.allowed)))
    while yices_ctx.check_context() == Status.SAT:
        model = Model.from_context(yices_ctx, 1)
        scenario = scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
        yield scenario
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

# Generate scenarios compatible with action 'required'
# constraints. WARNING: see note about yices context on genAllowedScenarios.
def genRequiredScenarios(yices_ctx: Context,                      # Yices context.
                        ctx: Mapping[Ident, Type],                # Typing context.
                        env: Mapping[Ident, Term],                # Map variables to yices terms.
                        fintype_els: Mapping[Ident, List[Ident]], # Names of FinType elements.
                        action: Action
                        ) -> Iterator[Scenario]:
    yices_ctx.push()
    yices_ctx.assert_formula(compileExpr(env, disj(action.required)))
    while yices_ctx.check_context() == Status.SAT:
        model = Model.from_context(yices_ctx, 1)
        scenario = scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
        yield scenario
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
