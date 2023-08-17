# Test tool on example system.

from control import Action, conj, eq, FinTypeDecl, Ident, neg, System, Type, UCA, VarDecl, when
# from parser import parseBytes
from solver import assertInvariants, checkConstraints, genScenarios, setupYicesContext
from tycheck import buildTypingCtx, tycheckSystem, tycheckUCA, TypeError
from typing import Any, Dict, List, Mapping, Optional, Tuple
from yices import Config, Context, Model, Status, Types, Terms

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

# NOTE: The above comment might be slightly out of sync with the
# actual system below.

# Test system.
sys: System = System(name = 'system',
                     types = [FinTypeDecl(name = 'DryOrWet', elements = ['dry', 'wet'])],
                     vars = [],
                     actions = [],
                     
                     components =
                     [System(name = 'aircraft',
                             types = [],
                             vars = [VarDecl('landing', 'bool')],
                             components = [],
                             actions = [Action(name = 'hit_brakes',
                                               constraints =
                                               [Ident.ofStr('system.aircraft.landing')])],
                             invariants = []),
                      System(name = 'environment',
                             types = [],
                             vars = [VarDecl('runway_status',
                                             Ident.ofStr('system.DryOrWet'))],
                             components = [],
                             actions = [],
                             invariants = ['true']),
                      System(name = 'wheels',
                             types = [],
                             vars = [VarDecl('weight_on_wheels', 'bool')],
                             components = [],
                             actions = [],
                             invariants = [])],
                     
                     invariants =
                     [when(conj([Ident.ofStr('system.aircraft.landing'),
                                 eq(Ident.ofStr('system.environment.runway_status'),
                                    Ident.ofStr('system.dry'))]),
                           Ident.ofStr('system.wheels.weight_on_wheels'))])

# UCA hit_brakes:
#   typ: issued
#   context: not wheels.weight_on_wheels
# UCA hit_brakes:
#   typ: not issued
#   context: aircraft.landing

# Test UCAs.
ucas: List[UCA] = [UCA(action = Ident.ofList(['system', 'aircraft', 'hit_brakes']),
                       type = 'issued',
                       context = neg(Ident.ofList(['system', 'wheels', 'weight_on_wheels']))),
                   UCA(action = Ident.ofList(['system', 'aircraft', 'hit_brakes']),
                       type = 'not issued',
                       context = Ident.ofList(['system', 'aircraft', 'landing']))]

# Check that the system is well-formed.
try:
    ctx: Mapping[Ident, Type] = buildTypingCtx(sys)
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

# # Load source program.
# src = open("test.stpa", "rb").read()
# sys = parseBytes(src)
