:warning: The code here is *not* released under an open source
license. Contact [abagnalla@gmail.com](abagnalla@gmail.com) to request
permission to use it. :warning:

This is a proof-of-concept SMT-based verification system (currently
using a [yices2](https://yices.csl.sri.com/) backend) for
[STPA](https://youtu.be/2W-iqnPbhyc?si=1iHmgzH7dk9rCDzm). It's based
on a very high-level model of control systems, similar to how they're
presented in the STPA handbook. There is currently no explicit
distinction between general variables (representing propositional
statements about the "real world") and process model variables
(representing controller "beliefs" about the real world). All
variables are general variables since they can be used express beliefs
anyway (but there may be good reason to distinguish between them for,
e.g., compiling constraints on process model variables to hardware
monitors to enforce them). There are also no behavioral models of the
actual control algorithms, so we don't do any kind of 'deep'
verification of actual system behavior. The tool just provides an aid
to the STPA analyst who is coming up with controller safety
constraints based on the high-level control structure and UCAs
identified in the STPA process. You might call this approach
"solver-aided controller constraint specification".

# The basic idea

1. The analyst goes through the usual STPA process specifying losses,
system-level hazards and constraints, the control structure, and
UCAs. Of these, only the control structure and UCAs are formalized
(although they should contain references to associated hazards/losses
for traceability).

2. Next is to specify constraints on individual control actions that
when enforced will prevent the UCA hazards. One way to obtain these is
to simply negate the UCAs, but as the STPA handbook says it's not
necessary to have a one-to-one correspondence between UCAs and
controller constraints. E.g., a single constraint might rule out
multiple UCAs. However, the analyst might make a mistake at this step
and create a constraint that doesn't quite rule out the UCA(s) as
intended. A solver can check automatically that the constraints do
indeed rule out the UCAs, or otherwise provide a counterexample system
state where the given constraints are satisfied but a UCA is still
possible.

# The value provided by the tool

- Formalizing the control system and constraints/assumptions forces
  the analyst to be think clearly and precisely about the analysis and
  to state all assumptions explicitly.

- The tool validates the model to ensure that it's well-formed.

- The tool catches logical mistakes made by the analyst when creating
  controller action constraints.

- The tool could make recommendations to fix constraints? Perhaps via
  some clever use of interpolants (supported by yices).

- If all the UCAs are verified successfully (proved impossible under
  the control action constraints), the tool can generate system states
  that are compatible with the constraints to help the analyst
  consider possibly hazardous scenarios that they may have missed,
  i.e., to discover more UCAs.

- The solver can be used iteratively and interactively. E.g., when the
  analyst adds a new UCA, the tool will immediately point out a
  hazardous scenario corresponding to the UCA that needs to be handled
  by a constraint. Then when a sufficient constraint is added, the
  tool can be used to look for more UCAs, and so on.

# System data structures

The following definitions are in [control.py](control.py).

## Actions

An action is just a name for the action and two lists of constraints
where each constraint is a Boolean expression:

```python
class Action:
    name:     str        # Name of action (e.g., CA1).
    allowed:  List[Expr] # Constraints for when action is allowed.
    required: List[Expr] # Constraints for when action is required.
```

* An action is said to be *allowed* when *all* of its `allowed`
constraints are satisfied.

* An action is said to be *required* when *any* of its `required`
constraints are satisfied.

Two special variables are automatically generated for each action `a`:
`a.allowed` and `a.required`. They can be referred to inside
constraint expressions. `a.allowed` is true iff the conjunction of
`a`'s `allowed` constraints is true, and `a.required` is true iff the
disjunction of `a`'s 'required' constraints is true. This enables a
kind of compositional reasoning for UCAs like "this action is
potentially hazardous when action `A` is allowed and action `B` is not
required".

## Systems

A system is encoded by the following data structure:

```python
class System:
    name:       str               # Name of system.
    types:      List[FinTypeDecl] # Type declarations.
    vars:       List[VarDecl]     # State of system.
    invariants: List[Expr]        # Invariant properties of internal
                                  # state and/or components.
    actions:    List[Action]      # Control actions that can be
                                  # performed by this system/component.
    components: List[System]      # Subsystems / components.
```

The 'state' of a system is a list of variables, each with a specified
type (currently 'bool', 'int', or an enum type). The type declarations
are for declaring enum types. The invariants are properties of the
internal state and/or subsystems that is expected to always hold (for
example, two variables of the state might always be related in some
way). The 'components' are subsystems that can be nested to arbitrary
depth (the subsystems may themselves be composed of subsystems and so
on).

### Identifiers

```python
class Ident:
    qualifier: Optional[Ident]
    name: str
```

An `Ident` is a unique identifier for a variable, action, or
system/component. For example, the identifier
`brakes_system.aircraft.hit_brakes` could denote the `hit_brakes`
action of component `aircraft` of system `brakes_system`.

## UCAs

```python
UCAType = Literal['issued', 'not issued']
class UCA:
    action:  Ident   # Name of action.
    type:    UCAType # Type of UCA.
    context: Expr    # Context in which action is potentially hazardous.
```

Currently only the first two types of UCAs are supported, but I think
the other two can actually be simulated via these two so they may be
the only ones necessary.

# Example system

The following is a small example system specified in a hypothetical
concrete syntax (a parser for this syntax isn't implemented -- the
system is currently encoded directly in the above data structures in
the file [run.py](run.py)).

```
system aircraft_brakes_system:
  type DryOrWet: {dry, wet}
  component aircraft:
    var landing: bool
    action hit_brakes:
      constraint: wheels.weight_on_wheels is true
  component environment:
    var runway_status: DryOrWet
  component wheels:
    var weight_on_wheels: bool
  assumption:
     when aircraft.landing is true and environment.runway_status is dry,
       wheels.weight_on_wheels is true
```

And a couple UCAs:

```
UCA aircraft.hit_brakes:
  type: issued
  context: wheels.weight_on_wheels is false
UCA aircraft.hit_brakes:
  type: not issued
  context: aircraft.landing is true
```

Running the verifier on the above system and UCAs (run `make` to
reproduce) produces the following output (see [solver.py](solver.py)
for the code that compiles expressions and invokes the yices solver):

```
Checking UCA(action=sys.aircraft.hit_brakes, type=issued, context={NOT sys.wheels.weight_on_wheels})
UCA verified!
Checking UCA(action=sys.aircraft.hit_brakes, type=not issued, context={sys.aircraft.landing})
Failed to verify UCA. Counterexample:
{sys.aircraft.landing: True, sys.aircraft.hit_brakes.allowed: True, sys.aircraft.hit_brakes.required: False, sys.environment.runway_status: sys.wet, sys.wheels.weight_on_wheels: False}

Scenarios in which action 'sys.aircraft.hit_brakes' is ALLOWED:
{sys.aircraft.landing: True, sys.aircraft.hit_brakes.allowed: True, sys.aircraft.hit_brakes.required: False, sys.environment.runway_status: sys.wet, sys.wheels.weight_on_wheels: False}
{sys.aircraft.landing: True, sys.aircraft.hit_brakes.allowed: True, sys.aircraft.hit_brakes.required: False, sys.environment.runway_status: sys.wet, sys.wheels.weight_on_wheels: True}
{sys.aircraft.landing: True, sys.aircraft.hit_brakes.allowed: True, sys.aircraft.hit_brakes.required: False, sys.environment.runway_status: sys.dry, sys.wheels.weight_on_wheels: True}

Scenarios in which action 'sys.aircraft.hit_brakes' is REQUIRED:
```

NOTE: currently all variables are required to be fully qualified. This
is not a fundamental limitation -- I just haven't implemented a
renamer pass yet to fill in missing qualifiers (some kind of namespace
import mechanism could be helpful as well).

# UCA verification

The solver does the following for each UCA of type 'issued' (where the
action is potentially hazardous when issued in the given context):

- Attempt to prove that there does not exist a system state in which
  the UCA context is true and the action is allowed or required.
  
- If successful, this means that the constraints do indeed rule out
  the hazard specified by the UCA.
  
- If unsuccessful, print out a counterexample system state in which
  either all the 'allowed' constraints are satisfied or one of the
  'required' constraints is satisfied but the hazard specified by the
  UCA is still possible.

And for each UCA of type 'not issued' (where the action is potentially
hazardous when **NOT** issued in the given context):

- Attempt to prove that there does not exist a system state in which
  the UCA context is true and the action is not allowed and not
  required.

- If successful, this means that no 'allowed' constraint ever prevents
  the action from being executed in the context specified by the UCA,
  and at least one 'required' constraint requires it to be executed..

- If unsuccessful, print out a system state in which the UCA context
  is satisfied (and so it would be hazardous to not execute the
  action) but also violates either violates one of the 'allowed'
  constraints which prohibits it from being executed or doesn't
  satisfy any of the 'required' constraints..

See the comments in [solver.py](solver.py) for mathematical details.

# Scenario generation

A scenario is a mapping from identifiers to values representing a
"possible world". A value is (for now) either a bool, int, or string
denoting a fintype element.

```python
class Scenario:
    dict: Dict[Ident, bool | int | Ident]
```

The tool can generate, for each action `a`, scenarios that are:
1) compatible with all of `a`'s `allowed` constraints, and
2) compatible with at least one of `a`'s `required` constraints.

When system variables are of finite types, it's always possible to
enumerate all scenarios. However, there could be very many scenarios,
or even worse, infinitely many when variables are of integer or real
type. To deal with this, the tool doesn't attempt to produce the
entire list of possible scenarios, but lazily produces scenarios via a
[generator](https://wiki.python.org/moin/Generators) that can be
stopped at any point. See the functions `genAllowedScenarios` and
`genRequiredScenarios` in [solver.py](solver.py)
