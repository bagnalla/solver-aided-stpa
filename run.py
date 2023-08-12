from yices import *

from control import Action, BinaryExpr, buildTypingCtx, Component, conj, disj, \
    eq, Expr, NamedType, IntLiteral, NameExpr, neg, System, tycheckSystem, tycheckUCA, \
    Type, TypeDecl, UCA, UnaryExpr, VarDecl, when

from typing import Dict, List, Tuple

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

def setupYicesContext(sys: System) -> Tuple[Context, Dict[str, any]]:
    yices_ctx = Context(Config())
    bool_t = Types.bool_type()
    int_t = Types.int_type()

    # Compilation environment mapping names (strings) to yices terms.
    env = {}
    # Map type names to yices types.
    types = {}

    # Declare enum types.
    for decl in sys.types:
        ty, terms = Types.declare_enum(decl.name, decl.elements)
        types[decl.name] = ty
        for el, t in zip(decl.elements, terms):
            env[el] = t

    # Declare component state variables.
    for c in sys.components:
        for var in c.state:
            match var.ty:
                case 'bool':
                    env['%s_%s' % (c.name, var.name)] = \
                        Terms.new_uninterpreted_term(bool_t, var.name)
                case 'int':
                    env['%s_%s' % (c.name, var.name)] = \
                        Terms.new_uninterpreted_term(int_t, var.name)
                case NamedType():
                    env['%s_%s' % (c.name, var.name)] = \
                        Terms.new_uninterpreted_term(types[var.ty.name], var.name)

    return yices_ctx, env

def getActionByName(sys: System, name: str) -> Action:
    for c in sys.components:
        for a in c.actions:
            if a.name == name:
                return a
    raise Exception('getActionByName: no action found with name %s' % name)

# Assert conjunction of all component state invariants:
# ⋀sys.assumptions and ⋀{c.invariant | c ∈ sys.components}.
def assertInvariants(yices_ctx: Context, env: Dict[str, any], sys: System):
    yices_ctx.assert_formulas([compileExpr(env, e) for e in sys.assumptions])
    yices_ctx.assert_formulas([compileExpr(env, c.invariant) for c in sys.components])

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

def checkConstraints(yices_ctx: Context,
                     env: Dict[str, any],
                     sys: System,
                     ucas: List[UCA]) -> bool:    
    for u in ucas:
        print('Checking %s' % u)
        yices_ctx.push()
        
        a = getActionByName(sys, u.action)

        if u.type == 'issued':
            yices_ctx.assert_formula(compileExpr(env, conj(a.constraints + [u.context])))
        else: # u.type == 'not_issued'
            yices_ctx.assert_formula(compileExpr(env, conj([u.context,
                                                            disj([neg(e)
                                                                  for e in a.constraints])])))
        
        status = yices_ctx.check_context()
        if status == Status.SAT:
            model = Model.from_context(yices_ctx, 1)
            model_string = model.to_string(80, 100, 0)
            print('Failed to verify UCA. Counterexample:')
            print(model_string)
            return False
        else:
            print('UCA verified!')
        
        yices_ctx.pop()

    return True

# TODO: If above succeeds, generate scenarios compatible with action constraints.
def genScenarios(yices_ctx: Context, sys: System):
    # TODO: For each action, assert conjunction of its constraints and
    # enumerate models (assignments of variables that satisfy all the
    # constraints while being consistent with all the component
    # invariants which are assumed to have already been asserted in
    # the given yices context).
    pass

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

# Test system.
sys: System = System(name = 'aircraft_brakes_system',
                     
                     types = [TypeDecl(name = 'DryOrWet',
                                       elements = ['dry', 'wet'])],
                     
                     components =
                     [Component(name = 'aircraft',
                                state = [VarDecl('landing', 'bool')],
                                invariant = 'true',
                                actions = [Action(name = 'hit_brakes',
                                                  constraints =
                                                  [NameExpr('wheels', 'weight_on_wheels')])]),
                      Component(name = 'environment',
                                state = [VarDecl('runway_status', NamedType('DryOrWet'))],
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
#   type: issued
#   context: not wheels.weight_on_wheels
# UCA hit_brakes:
#   type: not issued
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
yices_ctx, env = setupYicesContext(sys)
assertInvariants(yices_ctx, env, sys)
if checkConstraints(yices_ctx, env, sys, ucas):
    genScenarios(yices_ctx, sys)
