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
sys: System = \
    System(name = 'sys',
           
           # Declare a 'FinType' (finite type, or enum) named
           # 'sys.DryOrWet' and has with elements 'sys.dry' and 'sys.wet'.
           types = [FinTypeDecl(name = 'DryOrWet', elements = ['dry', 'wet'])],
           
           # No variables associated with the 'sys' system.
           vars = [],
           
           # No actions associated with the 'sys' system.
           actions = [],
           
           # The 'sys' system has three components: 'sys.aircraft',
           # 'sys.environment', and 'sys.wheels' (perhaps the wheels
           # should be a component of the aircraft instead).
           components =
           
           # 'sys.aircraft' system.
           [System(name = 'aircraft',
                   types = [],
                   
                   # The 'aircraft' component has a single Boolean
                   # variable called 'sys.aircraft.landing' denoting
                   # whether the aircraft is currently landing.
                   vars = [VarDecl('landing', 'bool')],
                   components = [],
                   
                   # The 'aircraft' component has a single action
                   # called 'aircraft.hit_brakes' with a single safety constraint.
                   actions = [Action(name = 'hit_brakes',
                                     
                                     # Variable 'sys.aircraft.landing' must be true
                                     # for the 'hit_brakes' action to be safe.
                                     constraints = [Ident.ofStr('sys.aircraft.landing')])],
                   
                   # No internal invariant for 'sys.aircraft'.
                   invariants = []),
            
            # 'sys.environment' system.
            System(name = 'environment',
                   types = [],
                   
                   # The environment has a single variable
                   # 'sys.environment.runway_status' with type 'sys.DryOrWet'.
                   vars = [VarDecl('runway_status', Ident.ofStr('sys.DryOrWet'))],
                   components = [],
                   actions = [],
                   
                   # Trivial invariant that is always true (equivalent
                   # to no invariant at all).
                   invariants = ['true']),
            
            # 'sys.wheels' system.
            System(name = 'wheels',
                   types = [],
                   vars = [VarDecl('weight_on_wheels', 'bool')],
                   components = [],
                   actions = [],
                   invariants = [])],
           
           # The 'sys' system has a single invariant:
           # 'when sys.aircraft.landing and
           # sys.environment.runway_status = sys.dry', sys.wheels.weight_on_wheels'
           
           # In prose: When the aircraft is landing and the runway is
           # dry, weight_on_wheels is true. This is an assumption we
           # have about the world.
           invariants =
           [when(conj([Ident.ofStr('sys.aircraft.landing'),
                       eq(Ident.ofStr('sys.environment.runway_status'),
                          Ident.ofStr('sys.dry'))]),
                 Ident.ofStr('sys.wheels.weight_on_wheels'))])

# UCA hit_brakes:
#   typ: issued
#   context: not wheels.weight_on_wheels
# UCA hit_brakes:
#   typ: not issued
#   context: aircraft.landing

    # Action 'sys.aircraft.hit_brakes' is potentially hazardous when
    # issued when 'sys.wheels.weight_on_wheels' is false.

# Test UCAs.
ucas: List[UCA] = \
    [UCA(action = Ident.ofStr('sys.aircraft.hit_brakes'),
         type = 'issued',
         # Action 'sys.aircraft.hit_brakes' is potentially hazardous
         # when issued when 'sys.wheels.weight_on_wheels' is false.
         context = neg(Ident.ofStr('sys.wheels.weight_on_wheels'))),
     
     UCA(action = Ident.ofStr('sys.aircraft.hit_brakes'),
         type = 'not issued',
         # Action 'sys.aircraft.hit_brakes' is potentially hazardous when
         # NOT issued when 'sys.aircraft.landing' is true.
         context = Ident.ofStr('sys.aircraft.landing'))]

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
