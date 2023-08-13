from yices import Config, Context, Model, Status, Types, Terms

from control import Action, BinaryExpr, buildTypingCtx, Component, conj, disj, \
    eq, Expr, FinType, IntLiteral, NameExpr, neg, System, tycheckSystem, tycheckUCA, \
    Type, TypeError, UCA, UnaryExpr, VarDecl, when

from typing import Any, Dict, List, Optional, Tuple

# This file is not typecheckable because yices doesn't provide static
# type information. We could provide a stub file for the yices
# definitions we use, I guess.

# Compile expressions to yices expressions.
def compileExpr(env: Dict, e: Expr):
    match e:
        case IntLiteral():
            return Terms.integer(e.i)
        case 'true':
            return Terms.true()
        case 'false':
            return Terms.false()
        case NameExpr():
            if str(e) in env:
                return env[str(e)]
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

def setupYicesContext(sys: System) -> Tuple[Context,        # Yices context.
                                            Dict[str, Any], # Yice term environment.
                                            List[str]]:     # FinType elements.
    yices_ctx = Context(Config())
    bool_t = Types.bool_type()
    int_t = Types.int_type()

    # Compilation environment mapping names (strings) to yices terms.
    env = {}
    # Map type names to yices types.
    types = {}
    # List of FinType elements.
    fintype_els = []

    # Declare enum types.
    for decl in sys.types:
        ty, terms = Types.declare_enum(decl.name, decl.elements)
        types[decl.name] = ty
        fintype_els += decl.elements
        for el, tm in zip(decl.elements, terms):
            env[el] = tm

    # Declare component state variables.
    for c in sys.components:
        for var in c.state:
            ident = '%s_%s' % (c.name, var.name)
            match var.ty:
                case 'bool':
                    env[ident] = Terms.new_uninterpreted_term(bool_t, ident)
                case 'int':
                    env[ident] = Terms.new_uninterpreted_term(int_t, ident)
                case FinType():
                    env[ident] = Terms.new_uninterpreted_term(types[var.ty.name], ident)

    return yices_ctx, env, fintype_els

def getActionByName(sys: System, name: str) -> Action:
    for c in sys.components:
        for a in c.actions:
            if a.name == name:
                return a
    raise Exception('getActionByName: no action found with name %s' % name)

# Assert conjunction of all component state invariants:
# ⋀sys.assumptions and ⋀{c.invariant | c ∈ sys.components}.
def assertInvariants(yices_ctx: Context, env: Dict[str, Any], sys: System):
    yices_ctx.assert_formulas([compileExpr(env, e) for e in sys.assumptions])
    yices_ctx.assert_formulas([compileExpr(env, c.invariant) for c in sys.components])

Scenario = Dict[str, bool | int | str]

def scenarioFromModel(yices_ctx: Context,     # Yices context.
                      ctx: Dict[str, Type],   # Typing context.
                      env: Dict[str, Any],    # Map variables to yices terms.
                      fintype_els: List[str], # Names of FinType elements.
                      model: Model            # Model produced by yices.
                      ) -> Scenario:          # Return scenario derived from model.
    defined_terms = model.collect_defined_terms()
    scenario: Scenario = {}
    for name, term in env.items():
        if name not in fintype_els and term in defined_terms:
            ty: Type = ctx[name]
            match ty:
                case 'bool':
                    scenario[name] = model.get_bool_value(term)
                case 'int':
                    scenario[name] = model.get_integer_value(term)
                case FinType():
                    scenario[name] = ty.elements[model.get_scalar_value(term)]
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

def checkConstraints(yices_ctx: Context,      # Yices context.
                     ctx: Dict[str, Type],    # Typing context.
                     env: Dict[str, Any],     # Map variables to yices terms.
                     fintype_els: List[str],  # Names of FinType elements.
                     sys: System,             # System to check.
                     ucas: List[UCA]          # UCAs to check.
                     ) -> Optional[Scenario]: # Return counterexample if found.
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
def genScenarios(yices_ctx: Context,             # Yices context.
                 ctx: Dict[str, Type],           # Typing context.
                 env: Dict[str, Any],            # Map variables to yices terms.
                 fintype_els: List[str],         # Names of FinType elements.
                 sys: System                     # System to generate scenarios for.
                 ) -> Dict[str, List[Scenario]]: # Map action names to # lists of scenarios
    
    # For each action, assert conjunction of its constraints and
    # enumerate models (assignments of variables that satisfy all the
    # constraints while being consistent with all the component
    # invariants which are assumed to have already been asserted in
    # the given yices context).
    
    scenarios: Dict[str, List[Scenario]] = {}
    for c in sys.components:
        for a in c.actions:
            # print('\nGenerating scenarios for action %s' % a)
            scenarios[a.name] = []
            yices_ctx.push()
            yices_ctx.assert_formulas([compileExpr(env, e) for e in a.constraints])
            while yices_ctx.check_context() == Status.SAT:
                model = Model.from_context(yices_ctx, 1)
                scenario = scenarioFromModel(yices_ctx, ctx, env, fintype_els, model)
                scenarios[a.name].append(scenario)
                # print(scenario)
                es: List[Expr] = []
                for name, val in scenario.items():
                    match ctx[name]:
                        case 'bool':
                            es.append(eq(NameExpr(None, name), 'true' if val else 'false'))
                        case 'int':
                            es.append(eq(NameExpr(None, name), IntLiteral(int(val))))
                        case FinType():
                            es.append(eq(NameExpr(None, name), NameExpr(None, str(val))))
                yices_ctx.assert_formula(compileExpr(env, neg(conj(es))))
            yices_ctx.pop()
    return scenarios

# system aircraft_brakes_system:
#   type DryOrWet: {dry, wet}
#   component aircraft:
#     var landing: bool
#     actions hit_brakes:
#       constraint: wheels.weight_on_wheels
#   component environment:
#     var runway_status: DryOrWet
#   component wheels:
#     var weight_on_wheels: bool
#   assumption:
#      when aircraft.landing = true and environment.runway_status = dry,
#        wheels.weight_on_wheels = true

dryOrWet = FinType(name = 'DryOrWet', elements = ['dry', 'wet'])

# Test system.
sys: System = System(name = 'aircraft_brakes_system',
                     
                     types = [dryOrWet],
                     
                     components =
                     [Component(name = 'aircraft',
                                state = [VarDecl('landing', 'bool')],
                                invariant = 'true',
                                actions = [Action(name = 'hit_brakes',
                                                  constraints =
                                                  [NameExpr('aircraft', 'landing')])]),
                      Component(name = 'environment',
                                state = [VarDecl('runway_status', dryOrWet)],
                                invariant = 'true',
                                actions = []),
                      Component(name = 'wheels',
                                state = [VarDecl('weight_on_wheels', 'bool')],
                                invariant = 'true',
                                actions = [])],
                     
                     assumptions =
                     [when(conj([NameExpr('aircraft', 'landing'),
                                 eq(NameExpr('environment', 'runway_status'),
                                    NameExpr(None, 'dry'))]),
                           NameExpr('wheels', 'weight_on_wheels'))])

# UCA hit_brakes:
#   typ: issued
#   context: not wheels.weight_on_wheels
# UCA hit_brakes:
#   typ: not issued
#   context: aircraft.landing

# Test UCAs.
ucas: List[UCA] = [UCA(action = 'hit_brakes',
                       type = 'issued',
                       context = neg(NameExpr('wheels', 'weight_on_wheels'))),
                   UCA(action = 'hit_brakes',
                       type = 'not issued',
                       context = NameExpr('aircraft', 'landing'))]

# Check that the system is well-formed.
try:
    ctx: Dict[str, Type] = buildTypingCtx(sys)
    tycheckSystem(sys, ctx)
    for u in ucas:
        tycheckUCA(u, ctx)
except TypeError as err:
    print(err.msg)
    exit(-1)

# Verify UCAs against system specification.
yices_ctx, env, fintype_els = setupYicesContext(sys)
assertInvariants(yices_ctx, env, sys)
counterexample = checkConstraints(yices_ctx, ctx, env, fintype_els, sys, ucas)
if counterexample:
    print('Failed to verify UCA. Counterexample:')
    print(counterexample)
# else:

print('\nConstraints:')
for c in sys.components:
    for a in c.actions:
        for e in a.constraints:
            print(e)

print('\nScenarios compatible with constraints:')
for action, scenarios in genScenarios(yices_ctx, ctx, env, fintype_els, sys).items():
    print("%s:" % action)
    for scen in scenarios:
        print('%s' % scen)

yices_ctx.dispose()
